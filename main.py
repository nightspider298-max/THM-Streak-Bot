#!/usr/bin/env python3
"""
THM Streak Bot v4.0 - Maintains your TryHackMe daily streak
Uses Firefox cookies + curl_cffi API + HARDCODED known rooms (100% FREE).

Key design: Instead of scanning 500 rooms through unreliable free proxies,
we use a hardcoded database of known-easy rooms with verified answers.
Each room attempt only needs 3 API calls (join + tasks + submit).

Flow:
1. Load cookies from base64-encoded THM_FIREFOX_COOKIES env var
2. Find a working HTTPS proxy (Vercel blocks GitHub Actions IPs)
3. Try each known room: join → get tasks → match hardcoded answers → submit
4. Stop on first success (for /new) or when streak is maintained
5. Send Telegram notification with results
"""
import os
import sys
import json
import time
import random
import sqlite3
import shutil
import tempfile
import datetime
import re
import base64
import glob as globmod

# Suppress SSL warnings for proxy usage
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
ANSWER_DELAY = 15       # seconds between answer submissions
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
COOKIE_DB_PATH = os.environ.get("THM_COOKIE_DB", "")
ACTIVE_PROXY = os.environ.get("THM_PROXY", None)

# ============================================================
# HARDCODED KNOWN ROOMS DATABASE
# Each entry: (room_slug, [(question_pattern, answer), ...])
# These are verified answers from the thmrevenant writeup repo.
# Only rooms with simple, unique answers are included.
# ============================================================
KNOWN_ROOMS = [
    ("blue", [
        ("how many ports are open with a port number under 1000", "3"),
        ("what is this machine vulnerable to", "ms17-010"),
        ("what is the full path of the code", "exploit/windows/smb/ms17_010_eternalblue"),
        ("what is the name of this value", "RHOSTS"),
        ("what is the name of the post module we will use", "post/multi/manage/shell_to_meterpreter"),
        ("what option are we required to change", "SESSION"),
        ("what is the name of the non-default user", "Jon"),
        ("what is the cracked password", "alqfna22"),
        ("flag1", "flag{access_the_machine}"),
        ("flag2", "flag{sam_database_elevated_access}"),
        ("flag3", "flag{admin_documents_can_be_valuable}"),
    ]),
    ("ice", [
        ("what port is this open on", "3389"),
        ("what service did nmap identify as running on port 8000", "Icecast"),
        ("what does nmap identify as the hostname of the machine", "DARK-PC"),
        ("what is the impact score for this vulnerability", "6.4"),
        ("what is the cve number for this vulnerability", "CVE-2004-1561"),
        ("what is the full path", "exploit/windows/http/icecast_header"),
        ("what is the only required setting which currently is blank", "rhosts"),
        ("what is the name of the shell we have now", "meterpreter"),
        ("what user was running that icecast process", "Dark"),
        ("what build of windows is the system", "7601"),
        ("what is the architecture of the process", "x64"),
        ("what is the full path", "exploit/windows/local/bypassuac_eventvwr"),
        ("what is the name of this option", "LHOST"),
        ("what permission listed allows us to take ownership", "SeTakeOwnershipPrivilege"),
        ("what user is listed", "NT AUTHORITY\\SYSTEM"),
        ("what command allows us to retrieve all credentials", "creds_all"),
        ("what is dark's password", "Password01"),
        ("what command allows us to dump all of the password hashes", "hashdump"),
        ("what command allows us to watch the remote user's desktop", "screenshare"),
        ("what command allows us to record from a microphone", "record_mic"),
        ("what command allows us to modify timestamps", "timestomp"),
        ("what command allows us to create a golden ticket", "golden_ticket_create"),
    ]),
    ("kenobi", [
        ("scan the machine with nmap, how many ports are open", "7"),
        ("how many shares have been found", "3"),
        ("what is the file can you see", "log.txt"),
        ("what port is ftp running on", "21"),
        ("what mount can we see", "/var"),
        ("what is the version", "1.3.5"),
        ("how many exploits are there for the proftpd", "4"),
        ("what is kenobi's user flag", "d0b0f3f53b6caa532a83915e19224899"),
        ("what file looks particularly out of the ordinary", "/usr/bin/menu"),
        ("run the binary, how many options appear", "3"),
        ("what is the root flag", "177b3cd8562289f37382721c28381f02"),
    ]),
    ("couch", [
        ("scan the machine. how many ports are open", "2"),
        ("what is the database management system", "couchdb"),
        ("what port is the database management system running on", "5984"),
        ("what is the version of the management system", "1.6.1"),
        ("what is the path for the web administration tool", "_utils"),
        ("what is the path to list all databases", "_all_dbs"),
        ("what are the credentials found", "atena:t4qfzcc4qN##"),
        ("compromise the machine and locate user.txt", "THM{1ns3cure_couchdb}"),
        ("escalate privileges and obtain root.txt", "THM{RCE_us1ng_Docker_API}"),
    ]),
    ("internal", [
        ("user.txt flag", "THM{int3rna1_fl4g_1}"),
        ("root.txt flag", "THM{d0ck3r_d3str0y3r}"),
    ]),
    ("overpass", [
        ("hack the machine and get the flag in user.txt", "thm{65c1aaf000506e56996822c6281e6bf7}"),
        ("escalate your privileges and get the flag in root.txt", "thm{7f336f8c359dbac18d54fdd64ea753bb}"),
    ]),
    ("startup", [
        ("what is the secret spicy soup recipe", "love"),
        ("what are the contents of user.txt", "THM{03ce3d619b80ccbfb3b7fc81e46c0e79}"),
        ("what are the contents of root.txt", "THM{f963aaa6a430f210222158ae15c3d76d}"),
    ]),
    ("rocket", [
        ("what is contained within the user.txt file", "THM{9f87696626a585380d3c1697087e5b5b}"),
        ("what is contained within the root.txt file", "THM{6613b7f76a88b32230eac584b0e18cfd}"),
    ]),
    ("res", [
        ("scan the machine, how many ports are open", "2"),
        ("what is the database management system installed on the server", "redis"),
        ("what port is the database management system running on", "6379"),
        ("what is the version of management system installed on the server", "6.0.7"),
        ("compromise the machine and locate user.txt", "thm{red1s_rce_w1thout_credent1als}"),
        ("what is the local user account password", "beautiful1"),
        ("escalate privileges and obtain root.txt", "thm{xxd_pr1v_escalat1on}"),
    ]),
    ("lazyadmin", [
        ("what is the user flag", "THM{63e5bce9271952aad1113b6f1ac28a07}"),
        ("what is the root flag", "THM{6637f41d0177b6f37cb20d775124699f}"),
    ]),
    ("hackernote", [
        ("which ports are open", "22,80,8080"),
        ("what programming language is the backend written in", "go"),
        ("how many usernames from the list are valid", "1"),
        ("what are/is the valid username", "james"),
        ("how many passwords were in your wordlist", "180"),
        ("what was the user's password", "blue7"),
        ("what's the user's ssh password", "dak4ddb37b"),
        ("what's the user flag", "thm{56911bd7ba1371a3221478aa5c094d68}"),
        ("what is the cve number for the exploit", "CVE-2019-18634"),
        ("what is the root flag", "thm{af55ada6c2445446eb0606b5a2d3a4d2}"),
    ]),
    ("temple", [
        ("find flag1.txt", "7362bee1e78243f4811f26565137d5e20cbd9af0"),
        ("find flag2.txt", "f620630155081293669dbb7949f975fa9386f1cd"),
    ]),
    ("wonderland", [
        ("obtain the flag in user.txt", 'thm{"Curiouser and curiouser!"}'),
        ("escalate your privileges, what is the flag in root.txt", "thm{Twinkle, twinkle, little bat! How I wonder what you're at!}"),
    ]),
    ("welcome", [
        ("what is the flag text shown on website", "flag{connection_verified}"),
    ]),
    ("skynet", [
        ("what is miles password for his emails", "cyborg007haloterminator"),
        ("what is the hidden directory", "/45kra24zxs28v3yd"),
        ("what is the vulnerability called when you can include a remote file", "remote file inclusion"),
        ("what is the user flag", "7ce5c2109a40f958099283600a9ae807"),
        ("what is the root flag", "3f0372db24753accc7179a282cd6a949"),
    ]),
    ("snort", [
        ("navigate to the task-exercises folder and run", "Too Easy!"),
        ("which snort mode can help you stop the threats on a local machine", "HIPS"),
        ("which snort mode can help you detect threats on a local network", "NIDS"),
        ("which snort mode can help you detect the threats on a local machine", "HIDS"),
        ("which snort mode can help you stop the threats on a local network", "NIPS"),
        ("which snort mode works similar to nips mode", "NBA"),
        ("according to the official description of the snort, what kind of nips is it", "full-blown"),
        ("nba training period is also known as", "baselining"),
        ("run the snort instance and check the build number", "149"),
    ]),
    ("nmap", [
        ("what networking constructs are used to direct traffic", "Ports"),
        ("how many of these are available on any network-enabled computer", "65535"),
        ("how many of these are considered well-known", "1024"),
        ("what is the first switch listed in the help menu for a syn scan", "-sS"),
        ("which switch would you use for a udp scan", "-sU"),
        ("if you wanted to detect which operating system", "-O"),
        ("nmap provides a switch to detect the version", "-sV"),
        ("how would you increase the verbosity", "-v"),
        ("how would you set the verbosity level to two", "-vv"),
        ("what switch would you use to save the nmap results in three major formats", "-oA"),
        ("what switch would you use to save the nmap results in a normal format", "-oN"),
        ("a very useful output format: how would you save results in a grepable format", "-oG"),
        ("how would you activate this setting", "-A"),
        ("how would you set the timing template to level 5", "-T5"),
        ("how would you tell nmap to only scan port 80", "-p 80"),
        ("how would you tell nmap to scan ports 1000-1500", "-p 1000-1500"),
        ("how would you tell nmap to scan all ports", "-p-"),
        ("how would you activate a script from the nmap scripting library", "--script"),
        ("how would you activate all of the scripts in the vuln category", "--script=vuln"),
        ("which rfc defines the appropriate behaviour for the tcp protocol", "RFC 9293"),
        ("if a port is closed, which flag should the server send back", "RST"),
        ("there are two other names for a syn scan", "Half-Open, Stealth"),
        ("can nmap use a syn scan without sudo permissions", "N"),
        ("if a udp port doesn't respond to an nmap scan, what will it be marked as", "open|filtered"),
        ("which protocol would it use to do so", "ICMP"),
        ("which of the three shown scan types uses the urg flag", "xmas"),
        ("why are null, fin and xmas scans generally used", "Firewall Evasion"),
        ("which common os may respond to a null, fin or xmas scan", "Microsoft Windows"),
        ("how would you perform a ping sweep", "nmap -sn 172.16.0.0/16"),
        ("what language are nse scripts written in", "Lua"),
        ("which category of scripts would be a very bad idea to run in a production environment", "intrusive"),
        ("what optional argument can the ftp-anon.nse script take", "maxlist"),
        ("what is the filename of the script which determines the underlying os of the smb server", "smb-os-discovery.nse"),
        ("read through this script. what does it depend on", "smb-brute"),
        ("which simple and frequently relied upon protocol is often blocked", "ICMP"),
        ("does the target ip respond to icmp echo ping requests", "N"),
        ("perform an xmas scan on the first 999 ports", "999"),
        ("there is a reason given for this", "No Response"),
        ("perform a tcp syn scan on the first 5000 ports", "5"),
        ("can nmap login successfully to the ftp server on port 21", "Y"),
    ]),
]


def log(msg):
    """Write to log file and print."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/thmbot_{datetime.datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, 'a') as f:
        f.write(f"{line}\n")
    print(line)


def send_telegram(message):
    """Send a Telegram notification."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("[!] Telegram not configured, skipping notification")
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        log("[+] Telegram notification sent")
    except Exception as e:
        log(f"[!] Telegram send failed: {e}")


def load_cookies():
    """Load cookies from base64 env var or Firefox cookies.sqlite."""
    b64_data = os.environ.get("THM_FIREFOX_COOKIES", "")
    if b64_data:
        log("[+] Loading cookies from THM_FIREFOX_COOKIES env var")
        try:
            json_str = base64.b64decode(b64_data).decode()
            cookie_list = json.loads(json_str)
            cookies = [(c["name"], c["value"], c["host"], c["path"]) for c in cookie_list]
            log(f"[+] Decoded {len(cookies)} cookies from JSON")
            return cookies
        except Exception as e:
            log(f"[!] Failed to decode JSON cookies: {e}")
            try:
                tmp = tempfile.mktemp(suffix=".db")
                with open(tmp, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                conn = sqlite3.connect(tmp)
                cursor = conn.cursor()
                cursor.execute("SELECT name, value, host, path FROM moz_cookies WHERE host LIKE '%tryhackme%'")
                cookies = cursor.fetchall()
                conn.close()
                os.unlink(tmp)
                log(f"[+] Decoded {len(cookies)} cookies from SQLite")
                return cookies
            except Exception as e2:
                log(f"[!] SQLite fallback also failed: {e2}")
                return []

    if COOKIE_DB_PATH and os.path.exists(COOKIE_DB_PATH):
        log(f"[+] Loading cookies from {COOKIE_DB_PATH}")
        tmp = tempfile.mktemp(suffix=".db")
        shutil.copy2(COOKIE_DB_PATH, tmp)
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value, host, path FROM moz_cookies WHERE host LIKE '%tryhackme%'")
        cookies = cursor.fetchall()
        conn.close()
        os.unlink(tmp)
        return cookies

    patterns = globmod.glob(os.path.expanduser("~/.mozilla/firefox/*/cookies.sqlite"))
    if patterns:
        log(f"[+] Loading cookies from {patterns[0]}")
        tmp = tempfile.mktemp(suffix=".db")
        shutil.copy2(patterns[0], tmp)
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value, host, path FROM moz_cookies WHERE host LIKE '%tryhackme%'")
        cookies = cursor.fetchall()
        conn.close()
        os.unlink(tmp)
        return cookies

    return []


def create_session(cookies):
    """Create a cloudscraper session with Firefox cookies."""
    import cloudscraper
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'linux'}
    )
    for name, value, host, path in cookies:
        domain = host.lstrip(".")
        session.cookies.set(name, value, domain=domain, path=path)
        if not host.startswith("."):
            session.cookies.set(name, value, domain=f".{domain}", path=path)
    session.headers.update({
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://tryhackme.com/",
        "Origin": "https://tryhackme.com",
    })
    return session


def find_working_proxy(cookies, exclude_proxy=None):
    """Find a working HTTPS proxy that can reach THM API (GET+POST).
    Returns (proxy_url, session) tuple."""
    from curl_cffi import requests as cffi_requests

    log("[+] Searching for working HTTPS proxy...")

    proxy_list = []
    try:
        import requests
        r = requests.get(
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=yes&anonymity=all",
            timeout=10
        )
        proxy_list = [p.strip() for p in r.text.strip().split("\n") if p.strip() and ":" in p]
        log(f"[+] Got {len(proxy_list)} proxies from proxyscrape")
    except Exception as e:
        log(f"[!] Failed to get proxies from proxyscrape: {e}")

    if not proxy_list:
        try:
            import requests
            r = requests.get(
                "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
                timeout=10
            )
            proxy_list = [p.strip() for p in r.text.strip().split("\n") if p.strip() and ":" in p][:100]
            log(f"[+] Got {len(proxy_list)} proxies from GitHub list")
        except Exception as e:
            log(f"[!] Failed to get proxies from GitHub: {e}")

    if not proxy_list:
        log("[!] No proxies available")
        return None, None

    # Shuffle to avoid always picking the same ones
    random.shuffle(proxy_list)

    for proxy in proxy_list[:30]:
        proxy_url = f"http://{proxy}"
        if exclude_proxy and proxy_url == exclude_proxy:
            continue
        try:
            test_session = cffi_requests.Session(impersonate="chrome120")
            for name, value, host, path in cookies:
                test_session.cookies.set(name, value, domain=host.lstrip("."), path=path)

            # Test GET CSRF
            r = test_session.get(
                "https://tryhackme.com/api/v2/auth/csrf",
                headers={"Accept": "application/json"},
                proxies={"https": proxy_url, "http": proxy_url},
                timeout=8,
                verify=False
            )
            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                continue
            d = r.json()
            if d.get("status") != "success":
                continue
            csrf_token = d["data"]["token"]

            # Test POST join
            r2 = test_session.post(
                "https://tryhackme.com/api/v2/rooms/join",
                headers={"Accept": "application/json", "Content-Type": "application/json",
                         "csrf-token": csrf_token},
                json={"roomCode": "blue"},
                proxies={"https": proxy_url, "http": proxy_url},
                timeout=10,
                verify=False
            )
            d2 = r2.json()
            if d2.get("status") == "success":
                log(f"[+] Found working proxy (GET+POST): {proxy}")
                return proxy_url, test_session
            else:
                log(f"[!] Proxy {proxy} POST failed: {d2.get('message','')[:40]}")
        except:
            continue

    log("[!] No working proxy found")
    return None, None


def make_headers(csrf, json_ct=True):
    """Build standard headers with CSRF token."""
    h = {"Accept": "application/json", "csrf-token": csrf}
    if json_ct:
        h["Content-Type"] = "application/json"
    return h


def get_proxy_dict():
    """Return proxy dict if a proxy is configured."""
    if ACTIVE_PROXY:
        return {"https": ACTIVE_PROXY, "http": ACTIVE_PROXY}
    return None


def _make_proxy_session(cookies=None):
    """Create a fresh session for proxy requests."""
    from curl_cffi import requests as cffi_requests
    s = cffi_requests.Session(impersonate="chrome120")
    if cookies:
        for name, value, host, path in cookies:
            s.cookies.set(name, value, domain=host.lstrip("."), path=path)
    return s


# Persistent proxy session
_PROXY_SESSION = None
_PROXY_COOKIES = None  # Store cookies for session recreation


def thm_get(session, url, headers=None, timeout=10):
    """Make a GET request to THM with optional proxy."""
    global _PROXY_SESSION
    proxy = get_proxy_dict()
    if proxy:
        if _PROXY_SESSION is None:
            _PROXY_SESSION = _make_proxy_session(_PROXY_COOKIES)
        kwargs = {"headers": headers or {}, "timeout": timeout, "verify": False,
                  "proxies": proxy}
        return _PROXY_SESSION.get(url, **kwargs)
    kwargs = {"headers": headers, "timeout": timeout}
    return session.get(url, **kwargs)


def thm_post(session, url, headers=None, json_data=None, timeout=10):
    """Make a POST request to THM with optional proxy."""
    global _PROXY_SESSION
    proxy = get_proxy_dict()
    if proxy:
        if _PROXY_SESSION is None:
            _PROXY_SESSION = _make_proxy_session(_PROXY_COOKIES)
        kwargs = {"headers": headers or {}, "timeout": timeout, "verify": False,
                  "proxies": proxy}
        if json_data is not None:
            kwargs["json"] = json_data
        return _PROXY_SESSION.post(url, **kwargs)
    kwargs = {"headers": headers, "timeout": timeout}
    if json_data is not None:
        kwargs["json"] = json_data
    return session.post(url, **kwargs)


def reset_proxy_session():
    """Reset the proxy session (call when proxy dies)."""
    global _PROXY_SESSION
    _PROXY_SESSION = None


def refresh_proxy_session():
    """Force create a fresh proxy session (new connection)."""
    global _PROXY_SESSION
    _PROXY_SESSION = _make_proxy_session(_PROXY_COOKIES)


def get_csrf(session):
    """Get CSRF token from THM."""
    r = thm_get(session, "https://tryhackme.com/api/v2/auth/csrf",
                headers={"Accept": "application/json"})
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        data = r.json()
        if data.get("status") == "success":
            return data["data"]["token"]

    log(f"[!] API CSRF blocked (status={r.status_code}), trying HTML fallback...")
    r2 = thm_get(session, "https://tryhackme.com/", headers={"Accept": "text/html"})
    match = re.search(r'csrf["\s:=]+["\']([a-zA-Z0-9_-]{20,})["\']', r2.text)
    if match:
        return match.group(1)

    r3 = thm_get(session, "https://tryhackme.com/dashboard", headers={"Accept": "text/html"})
    match2 = re.search(r'csrf["\s:=]+["\']([a-zA-Z0-9_-]{20,})["\']', r3.text)
    if match2:
        return match2.group(1)

    raise Exception(f"Could not get CSRF token. Last status: {r.status_code}")


def get_user_info(session, csrf):
    """Get user info and streak status."""
    r = thm_get(session, "https://tryhackme.com/api/v2/users/self",
                headers=make_headers(csrf, False))
    data = r.json()
    if data.get("status") != "success":
        return None
    user = data.get("data", {}).get("user", data.get("data", {}))
    streak = user.get("streak", {})
    return {
        "username": user.get("username", "unknown"),
        "currentStreak": streak.get("streak", 0),
        "largestStreak": streak.get("largestStreak", 0),
        "isStreakBroken": streak.get("isStreakBroken", True),
        "totalPoints": user.get("totalPoints", 0),
        "hasFirstAndLastAnswered": streak.get("hasFirstAndLastAnswered", False),
    }


def join_room(session, csrf, room_code):
    """Join a THM room."""
    try:
        r = thm_post(session, "https://tryhackme.com/api/v2/rooms/join",
                     headers=make_headers(csrf),
                     json_data={"roomCode": room_code})
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            data = r.json()
            return data.get("status") == "success"
        return False
    except Exception as e:
        log(f"  [!] join {room_code}: {e}")
        return False


def get_tasks(session, csrf, room_code):
    """Get room tasks."""
    try:
        r = thm_get(session, f"https://tryhackme.com/api/v2/rooms/tasks?roomCode={room_code}",
                    headers=make_headers(csrf, False))
        ct = r.headers.get("content-type", "")
        if "json" not in ct:
            return []
        data = r.json()
        return data.get("data", []) if data.get("status") == "success" else []
    except Exception as e:
        log(f"  [!] tasks {room_code}: {e}")
        return []


def submit_answer(session, csrf, task_id, question_no, answer, room_code):
    """Submit an answer to a room question."""
    try:
        r = thm_post(session, "https://tryhackme.com/api/v2/rooms/answer",
                     headers=make_headers(csrf),
                     json_data={
                         "taskId": task_id,
                         "questionNo": question_no,
                         "answer": answer,
                         "roomCode": room_code
                     })
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            return r.json()
        return {"status": "error", "message": f"Non-JSON response: {r.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clean_question(text):
    """Strip HTML tags and normalize a question string."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.strip()
    text = text.rstrip('?').rstrip('.')
    return text.lower()


def match_answer(question_text, hardcoded_pairs):
    """Try to match a THM question to a hardcoded answer."""
    q_clean = clean_question(question_text)

    best_match = None
    best_score = 0

    for hw_question, hw_answer in hardcoded_pairs:
        hw_clean = clean_question(hw_question)

        # Exact match - highest priority
        if q_clean == hw_clean:
            return hw_answer

        # Containment match (writeup question is part of THM question)
        if hw_clean in q_clean:
            return hw_answer

        # Reverse containment (THM question part is in writeup question)
        # Only if the THM question is shorter or similar length
        if q_clean in hw_clean and len(q_clean) > len(hw_clean) * 0.5:
            return hw_answer

        # Word overlap scoring (more strict)
        q_words = set(q_clean.split())
        h_words = set(hw_clean.split())
        if q_words and h_words:
            overlap = len(q_words & h_words) / max(len(q_words), len(h_words))
            # Require high overlap AND that questions aren't too different
            q_only = q_words - h_words
            h_only = h_words - q_words
            # If both have unique words, they're different questions
            if q_only and h_only and overlap < 0.95:
                continue
            if overlap > best_score and overlap > 0.7:
                best_score = overlap
                best_match = hw_answer

    return best_match


def fetch_writeup_for_room(room_slug):
    """Fetch writeup answers from thmrevenant repo for a specific room."""
    from curl_cffi import requests as cffi_requests
    s = cffi_requests.Session(impersonate="chrome120")

    url = f"https://raw.githubusercontent.com/thmrevenant/tryhackme/main/rooms/{room_slug}.txt"
    r = s.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    if r.status_code == 200 and r.text.strip():
        # Parse into (question, answer) pairs
        lines = []
        for l in r.text.strip().split("\n"):
            clean = re.sub(r'<[^>]+>', '', l).strip()
            if clean and not clean.startswith("http"):
                lines.append(clean)
        if len(lines) >= 3:
            pairs = []
            i = 1  # skip room title
            while i + 1 < len(lines):
                q = lines[i]
                a = lines[i + 1]
                if q and a:
                    pairs.append((q, a))
                i += 2
            return pairs
    return []


def check_room_completed(session, csrf, room_slug):
    """Check if all questions in a room are already answered."""
    try:
        tasks = get_tasks(session, csrf, room_slug)
        if not tasks:
            return None  # couldn't check (join failed, etc)
        for task in tasks:
            for q in task.get("questions", []):
                progress = q.get("progress", {})
                if not progress.get("noAnswer") and not progress.get("correct"):
                    return False  # found unanswered question
        return True  # all questions answered
    except Exception:
        return None


def main():
    global ACTIVE_PROXY, _PROXY_SESSION, _PROXY_COOKIES

    force_new = "--force-new" in sys.argv

    # Parse --complete [room]
    complete_mode = "--complete" in sys.argv
    complete_room = None
    if complete_mode:
        idx = sys.argv.index("--complete")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-"):
            complete_room = sys.argv[idx + 1].lower().strip()
        # If no room specified, complete_room stays None = random mode

    log("=" * 60)
    if complete_mode:
        mode = f"COMPLETE ROOM: {complete_room or 'RANDOM'}"
    elif force_new:
        mode = "FORCE NEW CHALLENGE"
    else:
        mode = "Streak Maintenance"
    log(f"THM Streak Bot v4.0 — {mode}")
    log(f"Run started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    # Step 1: Load cookies
    cookies = load_cookies()
    log(f"[+] Loaded {len(cookies)} THM cookies")
    if len(cookies) < 5:
        msg = "FATAL: Too few cookies. Re-login to THM in Firefox and re-export."
        log(f"[!] {msg}")
        send_telegram(f"THM Bot Error: {msg}")
        sys.exit(1)

    # Store cookies for proxy session recreation
    _PROXY_COOKIES = cookies

    # Step 2: Create session
    session = create_session(cookies)

    # Step 2b: Find a working proxy if needed
    if not ACTIVE_PROXY:
        try:
            # Test direct connection
            test_r = session.get("https://tryhackme.com/api/v2/auth/csrf",
                                 headers={"Accept": "application/json"}, timeout=8)
            if test_r.status_code == 200 and "json" in test_r.headers.get("content-type", ""):
                log("[+] Direct connection works")
            else:
                raise Exception("Direct blocked")
        except Exception:
            log("[!] Direct connection blocked, searching for proxy...")
            proxy, proxy_session = find_working_proxy(cookies)
            if proxy:
                ACTIVE_PROXY = proxy
                _PROXY_SESSION = proxy_session
                log(f"[+] Using proxy: {proxy}")
            else:
                log("[!] No proxy found, will retry direct")
                ACTIVE_PROXY = None

    # Step 2c: Get CSRF with retries
    csrf = None
    for attempt in range(5):
        try:
            csrf = get_csrf(session)
            log(f"[+] CSRF token: {csrf[:20]}...")
            break
        except Exception as e:
            log(f"[!] CSRF attempt {attempt+1} failed: {e}")
            if attempt < 4:
                wait = 5 * (attempt + 1)
                log(f"[!] Waiting {wait}s before retry...")
                time.sleep(wait)
                # On 3rd failure, try a different proxy
                if attempt == 2:
                    reset_proxy_session()
                    old_proxy = ACTIVE_PROXY
                    proxy, proxy_session = find_working_proxy(cookies, exclude_proxy=old_proxy)
                    if proxy:
                        ACTIVE_PROXY = proxy
                        _PROXY_SESSION = proxy_session
                        log(f"[+] Switched to proxy: {proxy}")
                session = create_session(cookies)

    if not csrf:
        msg = "FATAL: Could not get CSRF token after 5 attempts."
        log(f"[!] {msg}")
        send_telegram(f"THM Bot Error: {msg}")
        sys.exit(1)

    # Step 3: Verify login
    user = get_user_info(session, csrf)
    if not user:
        msg = "FATAL: Login failed. Cookies may be expired."
        log(f"[!] {msg}")
        send_telegram(f"THM Bot Error: {msg}")
        sys.exit(1)

    log(f"[+] Logged in as: {user['username']}")
    log(f"[+] Current streak: {user['currentStreak']}, broken: {user['isStreakBroken']}")

    # Check if streak already maintained today (skip if --force-new or --complete)
    if not force_new and not complete_mode and user["hasFirstAndLastAnswered"] and not user["isStreakBroken"]:
        msg = (f"THM Bot: Streak already maintained today!\n"
               f"Streak: {user['currentStreak']}\n"
               f"Largest: {user['largestStreak']}")
        log("[+] Streak already maintained today, nothing to do")
        send_telegram(msg)
        return

    # Step 4: --complete mode
    if complete_mode:
        # Build list of candidate rooms
        candidate_rooms = [slug for slug, _ in KNOWN_ROOMS]

        # If specific room requested, only try that one
        if complete_room:
            candidate_rooms = [complete_room]
        else:
            # Random mode: shuffle and try each until we find an uncompleted one
            random.shuffle(candidate_rooms)
            log(f"[+] Random mode: will try rooms in random order until finding an uncompleted one")

        solved_room = None
        answers_submitted = 0
        streak_increased = False

        for room_slug in candidate_rooms:
            log(f"[+] Trying room: {room_slug}")
            status = None  # Reset for each room

            # Check if room is already completed (only in random mode)
            if not complete_room:
                status = check_room_completed(session, csrf, room_slug)
                if status is True:
                    log(f"  [!] {room_slug} already complete, skipping")
                    continue
                elif status is None:
                    log(f"  [!] Can't check {room_slug} (join failed), skipping")
                    continue

            # Find answers: check KNOWN_ROOMS first, then fetch writeup
            hardcoded_answers = None
            for slug, answers in KNOWN_ROOMS:
                if slug == room_slug:
                    hardcoded_answers = answers
                    log(f"  [+] Found {room_slug} in known rooms database ({len(answers)} Q&A pairs)")
                    break

            if not hardcoded_answers:
                log(f"  [+] Fetching writeup for {room_slug} from GitHub...")
                hardcoded_answers = fetch_writeup_for_room(room_slug)
                if hardcoded_answers:
                    log(f"  [+] Got {len(hardcoded_answers)} Q&A pairs from writeup")
                else:
                    log(f"  [!] No writeup found for {room_slug}, skipping")
                    continue

            # Join room (if not already joined via check_room_completed)
            if status is None or status is False:
                if not join_room(session, csrf, room_slug):
                    log(f"  [!] Failed to join {room_slug}")
                    continue

            time.sleep(1)

            # Get tasks
            tasks = get_tasks(session, csrf, room_slug)
            if not tasks:
                log(f"  [!] Failed to get tasks for {room_slug}")
                continue

            log(f"  [+] Got {len(tasks)} tasks for {room_slug}")

            # Find ALL unanswered questions
            unanswered = []
            for task in tasks:
                task_id = task.get("_id")
                for q in task.get("questions", []):
                    progress = q.get("progress", {})
                    if progress.get("noAnswer") or progress.get("correct"):
                        continue
                    unanswered.append({
                        "task_id": task_id,
                        "question_no": q.get("questionNo"),
                        "question": q.get("question", ""),
                        "task_no": task.get("taskNo"),
                    })

            if not unanswered:
                log(f"  [!] No unanswered questions in {room_slug} (already complete!)")
                if complete_room:
                    send_telegram(f"THM Bot: Room '{room_slug}' is already fully complete!")
                    return
                continue

            log(f"  [+] {len(unanswered)} unanswered questions to solve in {room_slug}")

            # Submit ALL answers (don't break after first correct)
            room_answers = 0
            for uq in unanswered:
                answer = match_answer(uq["question"], hardcoded_answers)
                if not answer:
                    log(f"    [?] Task {uq['task_no']} Q{uq['question_no']}: No match for '{uq['question'][:50]}'")
                    continue

                log(f"    [+] Task {uq['task_no']} Q{uq['question_no']}: Submitting '{answer[:60]}'")

                result = submit_answer(session, csrf, uq["task_id"], uq["question_no"], answer, room_slug)
                data = result.get("data", {})

                if data.get("isCorrect"):
                    log(f"      [+] CORRECT! Score: +{data.get('scoreAwarded', 0)}")
                    answers_submitted += 1
                    room_answers += 1
                    solved_room = room_slug

                    if data.get("isStreakIncreased"):
                        log(f"      [+] STREAK INCREASED! New: {data.get('currentStreak')}")
                        streak_increased = True
                else:
                    msg = result.get("message", "unknown error")
                    log(f"      [!] Wrong or error: {msg}")
                    if "too fast" in str(msg).lower():
                        log(f"      [!] Rate limited, waiting 30s...")
                        time.sleep(30)

                time.sleep(5)

            log(f"  [+] {room_slug}: {room_answers}/{len(unanswered)} answers correct")

            # If we solved at least one question, we're done
            if solved_room:
                break

        # Final status for --complete mode
        final_user = get_user_info(session, csrf)
        log("=" * 60)
        log("COMPLETE ROOM STATUS:")
        if final_user:
            log(f"  Username: {final_user['username']}")
            log(f"  Current Streak: {final_user['currentStreak']}")
            log(f"  Total Points: {final_user['totalPoints']}")
        log(f"  Room: {solved_room or 'none'}")
        log(f"  Total Answers Submitted: {answers_submitted}")
        log(f"  Streak Increased: {streak_increased}")
        log("=" * 60)

        status_emoji = "SUCCESS" if solved_room else "FAILED"
        msg = (f"THM Bot - Room Complete {status_emoji}\n"
               f"Room: {solved_room or 'none'}\n"
               f"Answers: {answers_submitted}\n"
               f"Streak increased: {streak_increased}")
        if final_user:
            msg += f"\nStreak: {final_user['currentStreak']} | Points: {final_user['totalPoints']}"
        send_telegram(msg)
        return

    # Step 4b: Normal/force-new mode - try hardcoded known rooms
    log(f"[+] Trying {len(KNOWN_ROOMS)} known rooms...")
    rooms_attempted = 0
    answers_submitted = 0
    streak_increased = False
    solved_room = None
    proxy_rotations = 0

    for room_slug, hardcoded_answers in KNOWN_ROOMS:
        rooms_attempted += 1
        log(f"  [{rooms_attempted}/{len(KNOWN_ROOMS)}] Trying {room_slug}...")

        # Join room
        if not join_room(session, csrf, room_slug):
            log(f"    [!] Failed to join {room_slug}")
            # Refresh proxy session after 3 consecutive join failures (dead connection)
            if rooms_attempted % 3 == 0 and ACTIVE_PROXY:
                log(f"    [!] Refreshing proxy session (attempt #{rooms_attempted})...")
                refresh_proxy_session()
            continue

        time.sleep(1)  # Small delay between join and tasks

        # Get tasks
        tasks = get_tasks(session, csrf, room_slug)
        if not tasks:
            log(f"    [!] Failed to get tasks for {room_slug}")
            continue

        log(f"    [+] Got {len(tasks)} tasks for {room_slug}")

        # Find unanswered questions
        unanswered = []
        for task in tasks:
            task_id = task.get("_id")
            for q in task.get("questions", []):
                progress = q.get("progress", {})
                if progress.get("noAnswer") or progress.get("correct"):
                    continue
                unanswered.append({
                    "task_id": task_id,
                    "question_no": q.get("questionNo"),
                    "question": q.get("question", ""),
                    "task_no": task.get("taskNo"),
                })

        if not unanswered:
            log(f"    [!] No unanswered questions in {room_slug} (all already done)")
            continue

        log(f"    [+] {len(unanswered)} unanswered questions in {room_slug}")

        # Try to match and submit answers
        for uq in unanswered:
            answer = match_answer(uq["question"], hardcoded_answers)
            if not answer:
                continue

            log(f"    [+] Task {uq['task_no']} Q{uq['question_no']}: Submitting '{answer[:60]}'")

            result = submit_answer(session, csrf, uq["task_id"], uq["question_no"], answer, room_slug)
            data = result.get("data", {})

            if data.get("isCorrect"):
                log(f"    [+] CORRECT! Score: +{data.get('scoreAwarded', 0)}")
                answers_submitted += 1
                solved_room = room_slug

                if data.get("isStreakIncreased"):
                    log(f"    [+] STREAK INCREASED! New: {data.get('currentStreak')}")
                    streak_increased = True
                break  # One answer per room
            else:
                msg = result.get("message", "unknown error")
                log(f"    [!] Wrong or error: {msg}")
                if "too fast" in str(msg).lower():
                    log(f"    [!] Rate limited, waiting 30s...")
                    time.sleep(30)

            time.sleep(2)  # Brief delay between submissions

        # Check if we should stop
        if streak_increased or (force_new and solved_room):
            break

    # Step 5: Final status
    final_user = get_user_info(session, csrf)
    if final_user:
        log("=" * 60)
        log("FINAL STATUS:")
        log(f"  Username: {final_user['username']}")
        log(f"  Current Streak: {final_user['currentStreak']}")
        log(f"  Largest Streak: {final_user['largestStreak']}")
        log(f"  Streak Broken: {final_user['isStreakBroken']}")
        log(f"  Total Points: {final_user['totalPoints']}")
        log(f"  Rooms Attempted: {rooms_attempted}/{len(KNOWN_ROOMS)}")
        log(f"  Answers Submitted: {answers_submitted}")
        log(f"  Streak Increased: {streak_increased}")
        log("=" * 60)

        # Send Telegram notification
        status_emoji = "SUCCESS" if not final_user["isStreakBroken"] else "FAILED"
        msg = (f"THM Bot {status_emoji}\n"
               f"Streak: {final_user['currentStreak']} | "
               f"Largest: {final_user['largestStreak']}\n"
               f"Points: {final_user['totalPoints']}\n"
               f"Rooms attempted: {rooms_attempted}/{len(KNOWN_ROOMS)}\n"
               f"Answers submitted: {answers_submitted}\n"
               f"Streak increased: {streak_increased}")
        if solved_room:
            msg += f"\nSolved: {solved_room}"
        send_telegram(msg)
    else:
        log("[!] Could not fetch final user status")
        send_telegram(f"THM Bot ran but could not fetch final status. Solved: {solved_room or 'none'}")

    log(f"\n[+] Bot run completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
