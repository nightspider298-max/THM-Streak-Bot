#!/usr/bin/env python3
"""
THM Streak Bot - Maintains your TryHackMe daily streak
Uses Firefox cookies + curl_cffi API + writeup repos (100% FREE).

Flow:
1. Load cookies from base64-encoded THM_FIREFOX_COOKIES env var
2. Find a working HTTPS proxy (Vercel blocks GitHub Actions IPs)
3. Fetch room codes from thmrevenant writeup repo
4. For each room: join → get tasks → find unanswered → match writeup answers → submit
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
ANSWER_DELAY = 15  # seconds between answer submissions
MAX_ROOMS_TO_CHECK = 500  # how many rooms to scan from writeup repo
WRITEUP_REPO = "https://raw.githubusercontent.com/thmrevenant/tryhackme/main/rooms"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
COOKIE_DB_PATH = os.environ.get("THM_COOKIE_DB", "")
# Global proxy (set at runtime if needed)
ACTIVE_PROXY = os.environ.get("THM_PROXY", None)


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
    # Method 1: Base64-encoded JSON cookie list from env (GitHub Actions)
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
            # Fallback: try as SQLite database
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

    # Method 2: Direct cookie DB path
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

    # Method 3: Find Firefox profile automatically
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
    Returns (proxy_url, session) tuple so the working session can be reused."""
    from curl_cffi import requests as cffi_requests

    log("[+] Searching for working HTTPS proxy...")

    # Get proxy list from free sources
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
        log("[!] No proxies available, will try direct connection")
        return None, None

    for proxy in proxy_list[:50]:
        proxy_url = f"http://{proxy}"
        if exclude_proxy and proxy_url == exclude_proxy:
            continue
        try:
            # Create fresh session for each test AND reuse it if valid
            test_session = cffi_requests.Session(impersonate="chrome120")
            for name, value, host, path in cookies:
                test_session.cookies.set(name, value, domain=host.lstrip("."), path=path)

            # Test with GET CSRF first
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

            # Now test POST join (some proxies work for GET but not POST)
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
                # Return the working session so caller can reuse it immediately
                return proxy_url, test_session
            else:
                log(f"[!] Proxy {proxy} works for GET but not POST: {d2.get('message','')[:40]}")
        except:
            continue

    log("[!] No working proxy found, will try direct connection")
    return None, None


def get_csrf(session):
    """Get CSRF token from THM."""
    r = thm_get(session, "https://tryhackme.com/api/v2/auth/csrf",
                headers={"Accept": "application/json"})
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        data = r.json()
        if data.get("status") == "success":
            return data["data"]["token"]
        raise Exception(f"CSRF fetch failed: {data}")

    # Fallback: Try to get CSRF from the main page HTML
    log(f"[!] API CSRF blocked (status={r.status_code}), trying HTML fallback...")
    r2 = thm_get(session, "https://tryhackme.com/", headers={"Accept": "text/html"})
    match = re.search(r'csrf["\s:=]+["\']([a-zA-Z0-9_-]{20,})["\']', r2.text)
    if match:
        return match.group(1)

    r3 = thm_get(session, "https://tryhackme.com/dashboard", headers={"Accept": "text/html"})
    match2 = re.search(r'csrf["\s:=]+["\']([a-zA-Z0-9_-]{20,})["\']', r3.text)
    if match2:
        return match2.group(1)

    raise Exception(f"Could not get CSRF token from any source. Last status: {r.status_code}")


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


def _make_proxy_session():
    """Create a session for proxy requests."""
    from curl_cffi import requests as cffi_requests
    return cffi_requests.Session(impersonate="chrome120")


# Persistent proxy session (reused across all requests)
_PROXY_SESSION = None


def thm_get(session, url, headers=None, timeout=30):
    """Make a GET request to THM with optional proxy."""
    global _PROXY_SESSION
    proxy = get_proxy_dict()
    if proxy:
        if _PROXY_SESSION is None:
            _PROXY_SESSION = _make_proxy_session()
            for c in session.cookies:
                _PROXY_SESSION.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
        kwargs = {"headers": headers or {}, "timeout": timeout, "verify": False,
                  "proxies": proxy}
        return _PROXY_SESSION.get(url, **kwargs)
    kwargs = {"headers": headers, "timeout": timeout}
    return session.get(url, **kwargs)


def thm_post(session, url, headers=None, json_data=None, timeout=30):
    """Make a POST request to THM with optional proxy."""
    global _PROXY_SESSION
    proxy = get_proxy_dict()
    if proxy:
        if _PROXY_SESSION is None:
            _PROXY_SESSION = _make_proxy_session()
            for c in session.cookies:
                _PROXY_SESSION.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
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


def code_to_thm(code):
    """Convert writeup repo room code to THM URL slug."""
    return code.lower().replace(" ", "-").replace("&", "and")


def fetch_writeup(room_code_orig):
    """Fetch writeup answers from thmrevenant repo."""
    from curl_cffi import requests as cffi_requests
    s = cffi_requests.Session(impersonate="chrome120")

    # Try original name
    url = f"{WRITEUP_REPO}/{room_code_orig.replace(' ', '%20')}.txt"
    r = s.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code == 200:
        return r.text.strip()

    # Try hyphenated lowercase
    thm_code = code_to_thm(room_code_orig)
    url2 = f"{WRITEUP_REPO}/{thm_code}.txt"
    r2 = s.get(url2, headers={"User-Agent": "Mozilla/5.0"})
    if r2.status_code == 200:
        return r2.text.strip()

    return None


def parse_writeup(writeup_text):
    """Parse writeup text into a list of (question_pattern, answer) pairs.

    Format is: RoomName, URL, (blank), Q1, A1, (blank), Q2, A2, ...
    We filter non-empty lines, skip first 2 (title + URL), then pair Q/A.
    """
    # Clean HTML and get non-empty lines
    lines = []
    for l in writeup_text.strip().split("\n"):
        clean = re.sub(r'<[^>]+>', '', l).strip()
        if clean and not clean.startswith("http"):
            lines.append(clean)

    # First line is room title — skip it
    if len(lines) < 3:
        return []

    # Lines after title: Q1, A1, Q2, A2, ...
    pairs = []
    i = 1  # skip room title
    while i + 1 < len(lines):
        question = lines[i]
        answer = lines[i + 1]
        if question and answer:
            pairs.append((question, answer))
        i += 2

    return pairs


def clean_question(text):
    """Strip HTML tags and normalize a question string."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.strip()
    text = text.rstrip('?').rstrip('.')
    return text.lower()


def match_answer(question_text, writeup_pairs):
    """Try to match a THM question to a writeup answer."""
    q_clean = clean_question(question_text)

    for wp_question, wp_answer in writeup_pairs:
        wq_clean = clean_question(wp_question)

        # Exact match
        if q_clean == wq_clean:
            return wp_answer

        # Containment match
        if q_clean in wq_clean or wq_clean in q_clean:
            return wp_answer

        # Word overlap (>60% overlap)
        q_words = set(q_clean.split())
        w_words = set(wq_clean.split())
        if q_words and w_words:
            overlap = len(q_words & w_words) / max(len(q_words), len(w_words))
            if overlap > 0.6:
                return wp_answer

    return None


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
        log(f"  [!] join {room_code}: non-json response (status={r.status_code})")
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


def fetch_room_codes():
    """Fetch room codes from writeup repo."""
    import requests as req_lib
    import os

    url = "https://api.github.com/repos/thmrevenant/tryhackme/git/trees/main?recursive=1"
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

    # Use GITHUB_TOKEN if available (avoids rate limiting on GHA)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        r = req_lib.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            codes = set()
            for item in tree:
                path = item.get("path", "")
                if path.startswith("rooms/") and path.endswith(".txt"):
                    code = path.replace("rooms/", "").replace(".txt", "")
                    codes.add(code)
            return sorted(codes)
        log(f"[!] Failed to fetch repo tree: {r.status_code}")
    except Exception as e:
        log(f"[!] Failed to fetch repo tree: {e}")

    # Fallback: try without auth
    try:
        r2 = req_lib.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}, timeout=15)
        if r2.status_code == 200:
            tree = r2.json().get("tree", [])
            codes = set()
            for item in tree:
                path = item.get("path", "")
                if path.startswith("rooms/") and path.endswith(".txt"):
                    code = path.replace("rooms/", "").replace(".txt", "")
                    codes.add(code)
            return sorted(codes)
    except Exception as e:
        log(f"[!] Fallback also failed: {e}")

    return []


def main():
    # Parse command line args
    force_new = "--force-new" in sys.argv

    log("=" * 60)
    mode = "FORCE NEW CHALLENGE" if force_new else "Streak Maintenance"
    log(f"THM Streak Bot v3.0 — {mode}")
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

    # Step 2: Create session
    session = create_session(cookies)

    # Step 2b: Find a working proxy if needed (Vercel blocks GitHub Actions IPs)
    global ACTIVE_PROXY
    proxy_for_csrf = None
    if not ACTIVE_PROXY:
        # Try direct connection first
        try:
            csrf_test = get_csrf(session)
            log(f"[+] Direct connection works, CSRF: {csrf_test[:20]}...")
        except Exception:
            log("[!] Direct connection blocked by Vercel, searching for proxy...")
            proxy, proxy_session = find_working_proxy(cookies)
            if proxy:
                proxy_for_csrf = proxy
                global _PROXY_SESSION
                _PROXY_SESSION = proxy_session  # Reuse the validated session
                log(f"[+] Using proxy for CSRF: {proxy}")
            else:
                log("[!] No proxy found, will retry direct connection")
    else:
        proxy_for_csrf = ACTIVE_PROXY

    # Step 2c: Get CSRF with retries
    csrf = None
    for attempt in range(5):
        try:
            if proxy_for_csrf and not ACTIVE_PROXY:
                ACTIVE_PROXY = proxy_for_csrf
            csrf = get_csrf(session)
            log(f"[+] CSRF token: {csrf[:20]}...")
            break
        except Exception as e:
            log(f"[!] CSRF attempt {attempt+1} failed: {e}")
            if attempt < 4:
                wait = 10 * (attempt + 1)  # 10s, 20s, 30s, 40s
                log(f"[!] Waiting {wait}s before retry...")
                time.sleep(wait)
                # Try finding a different proxy on retry
                if attempt == 2 and not ACTIVE_PROXY:
                    proxy, proxy_session = find_working_proxy(cookies)
                    if proxy:
                        proxy_for_csrf = proxy
                        ACTIVE_PROXY = proxy
                        _PROXY_SESSION = proxy_session  # Reuse the validated session
                        log(f"[+] Switching to proxy: {proxy}")
                session = create_session(cookies)
    
    if not csrf:
        msg = "FATAL: Could not get CSRF token after 5 attempts. Vercel may be blocking GitHub Actions IPs."
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

    # Check if streak already maintained today (skip if --force-new)
    if not force_new and user["hasFirstAndLastAnswered"] and not user["isStreakBroken"]:
        msg = (f"THM Bot: Streak already maintained today!\n"
               f"Streak: {user['currentStreak']}\n"
               f"Largest: {user['largestStreak']}")
        log("[+] Streak already maintained today, nothing to do")
        send_telegram(msg)
        return

    # Step 4: Fetch room codes from writeup repo
    log("[+] Fetching room codes from writeup repo...")
    all_codes = fetch_room_codes()
    log(f"[+] Got {len(all_codes)} room codes from repo")

    if not all_codes:
        msg = "FATAL: Could not fetch room codes from writeup repo."
        log(f"[!] {msg}")
        send_telegram(f"THM Bot Error: {msg}")
        sys.exit(1)

    # Step 5: Scan rooms for unanswered questions with writeup answers
    log("[+] Scanning rooms for answerable questions...")
    rooms_checked = 0
    answers_submitted = 0
    streak_increased = False
    solved_room = None
    rooms_failed = 0

    consecutive_failures = 0
    for idx, code in enumerate(all_codes[:MAX_ROOMS_TO_CHECK]):
        thm_code = code_to_thm(code)

        # Rotate proxy after 5 consecutive failures (proxy may have been blocked)
        if consecutive_failures >= 5 and ACTIVE_PROXY:
            log(f"  [!] Rotating proxy after {consecutive_failures} consecutive failures...")
            old_proxy = ACTIVE_PROXY
            reset_proxy_session()
            new_proxy, new_session = find_working_proxy(cookies, exclude_proxy=old_proxy)
            if new_proxy:
                ACTIVE_PROXY = new_proxy
                _PROXY_SESSION = new_session  # Reuse the validated session
                log(f"[+] Switched to new proxy: {new_proxy}")
                consecutive_failures = 0
            else:
                log("[!] No new proxy found, continuing with current one")

        # Join room
        if not join_room(session, csrf, thm_code):
            rooms_failed += 1
            consecutive_failures += 1
            if rooms_failed <= 3:
                log(f"  [!] Failed to join {thm_code} (room {idx+1})")
            elif rooms_failed == 4:
                log(f"  [!] ... suppressing further join failure logs")
            continue

        # Get tasks
        tasks = get_tasks(session, csrf, thm_code)
        if not tasks:
            rooms_failed += 1
            consecutive_failures += 1
            if rooms_failed <= 3:
                log(f"  [!] Failed to get tasks for {thm_code}")
            continue

        consecutive_failures = 0  # Reset on success

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
            rooms_checked += 1
            continue

        # Fetch writeup for this room
        writeup = fetch_writeup(code)
        if not writeup:
            rooms_checked += 1
            continue

        writeup_pairs = parse_writeup(writeup)
        if not writeup_pairs:
            rooms_checked += 1
            continue

        # Try to match and submit answers
        for uq in unanswered:
            answer = match_answer(uq["question"], writeup_pairs)
            if not answer:
                continue

            log(f"[+] {thm_code} - Task {uq['task_no']} Q{uq['question_no']}: Submitting '{answer[:50]}'")

            result = submit_answer(session, csrf, uq["task_id"], uq["question_no"], answer, thm_code)
            data = result.get("data", {})

            if data.get("isCorrect"):
                log(f"  [+] CORRECT! Score: +{data.get('scoreAwarded', 0)}")
                answers_submitted += 1
                solved_room = thm_code

                if data.get("isStreakIncreased"):
                    log(f"  [+] STREAK INCREASED! New: {data.get('currentStreak')}")
                    streak_increased = True
                break  # One answer per room is enough
            else:
                msg = result.get("message", "unknown error")
                log(f"  [!] Wrong or error: {msg}")
                if "too fast" in str(msg).lower():
                    log(f"  [!] Rate limited, waiting 30s...")
                    time.sleep(30)

            time.sleep(ANSWER_DELAY)

        if streak_increased or (force_new and solved_room):
            break

        rooms_checked += 1
        if rooms_checked % 20 == 0:
            log(f"  ... checked {rooms_checked} rooms, {answers_submitted} answers submitted")

    # Step 6: Final status
    final_user = get_user_info(session, csrf)
    log("=" * 60)
    log("FINAL STATUS:")
    log(f"  Username: {final_user['username']}")
    log(f"  Current Streak: {final_user['currentStreak']}")
    log(f"  Largest Streak: {final_user['largestStreak']}")
    log(f"  Streak Broken: {final_user['isStreakBroken']}")
    log(f"  Total Points: {final_user['totalPoints']}")
    log(f"  Rooms Checked: {rooms_checked}")
    log(f"  Rooms Failed (join/task): {rooms_failed}")
    log(f"  Answers Submitted: {answers_submitted}")
    log(f"  Streak Increased: {streak_increased}")
    log("=" * 60)

    # Step 7: Send Telegram notification
    status_emoji = "SUCCESS" if not final_user["isStreakBroken"] else "FAILED"
    msg = (f"THM Bot {status_emoji}\n"
           f"Streak: {final_user['currentStreak']} | "
           f"Largest: {final_user['largestStreak']}\n"
           f"Points: {final_user['totalPoints']}\n"
           f"Rooms checked: {rooms_checked}\n"
           f"Answers submitted: {answers_submitted}\n"
           f"Streak increased: {streak_increased}")
    if solved_room:
        msg += f"\nSolved: {solved_room}"
    send_telegram(msg)

    log(f"\n[+] Bot run completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
