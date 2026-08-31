#!/usr/bin/env python3
"""
THM Streak Bot - Maintains your TryHackMe daily streak
Uses Firefox cookies + curl_cffi API + writeup repos (100% FREE).

Flow:
1. Load cookies from base64-encoded THM_FIREFOX_COOKIES env var
2. Fetch room codes from thmrevenant writeup repo
3. For each room: join → get tasks → find unanswered → match writeup answers → submit
4. Send Telegram notification with results
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

# --- Configuration ---
ANSWER_DELAY = 15  # seconds between answer submissions
MAX_ROOMS_TO_CHECK = 500  # how many rooms to scan from writeup repo
WRITEUP_REPO = "https://raw.githubusercontent.com/thmrevenant/tryhackme/main/rooms"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
COOKIE_DB_PATH = os.environ.get("THM_COOKIE_DB", "")


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
    """Create a curl_cffi session with Firefox cookies."""
    from curl_cffi import requests as cffi_requests
    session = cffi_requests.Session(impersonate="chrome120")
    for name, value, host, path in cookies:
        # Set cookie with both dotted and non-dotted domain for maximum compatibility
        domain = host.lstrip(".")
        session.cookies.set(name, value, domain=domain, path=path)
        # Also try with leading dot if not already present
        if not host.startswith("."):
            session.cookies.set(name, value, domain=f".{domain}", path=path)
    return session


def get_csrf(session):
    """Get CSRF token from THM."""
    r = session.get("https://tryhackme.com/api/v2/auth/csrf",
                     headers={"Accept": "application/json"})
    ct = r.headers.get("content-type", "")
    if "json" not in ct:
        # Might be getting Vercel challenge or HTML page
        log(f"[!] CSRF endpoint returned non-JSON: CT={ct[:50]}")
        log(f"[!] Response body: {r.text[:200]}")
        raise Exception(f"CSRF endpoint returned non-JSON: {r.status_code}")
    data = r.json()
    if data.get("status") == "success":
        return data["data"]["token"]
    raise Exception(f"CSRF fetch failed: {data}")


def make_headers(csrf, json_ct=True):
    """Build standard headers with CSRF token."""
    h = {"Accept": "application/json", "csrf-token": csrf}
    if json_ct:
        h["Content-Type"] = "application/json"
    return h


def get_user_info(session, csrf):
    """Get user info and streak status."""
    r = session.get("https://tryhackme.com/api/v2/users/self",
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
    r = session.post("https://tryhackme.com/api/v2/rooms/join",
                     headers=make_headers(csrf),
                     json={"roomCode": room_code})
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        data = r.json()
        return data.get("status") == "success"
    return False


def get_tasks(session, csrf, room_code):
    """Get room tasks."""
    r = session.get(f"https://tryhackme.com/api/v2/rooms/tasks?roomCode={room_code}",
                     headers=make_headers(csrf, False))
    ct = r.headers.get("content-type", "")
    if "json" not in ct:
        return []
    data = r.json()
    return data.get("data", []) if data.get("status") == "success" else []


def submit_answer(session, csrf, task_id, question_no, answer, room_code):
    """Submit an answer to a room question."""
    r = session.post("https://tryhackme.com/api/v2/rooms/answer",
                     headers=make_headers(csrf),
                     json={
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
    from curl_cffi import requests as cffi_requests
    s = cffi_requests.Session(impersonate="chrome120")

    r = s.get("https://api.github.com/repos/thmrevenant/tryhackme/git/trees/main?recursive=1",
              headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        log(f"[!] Failed to fetch repo tree: {r.status_code}")
        return []

    tree = r.json().get("tree", [])
    codes = set()
    for item in tree:
        path = item.get("path", "")
        if path.startswith("rooms/") and path.endswith(".txt"):
            code = path.replace("rooms/", "").replace(".txt", "")
            codes.add(code)

    return sorted(codes)


def main():
    log("=" * 60)
    log("THM Streak Bot v3.0 - Cookie + Writeup (FREE)")
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

    # Step 2b: Get CSRF with retries
    csrf = None
    for attempt in range(3):
        try:
            csrf = get_csrf(session)
            log(f"[+] CSRF token: {csrf[:20]}...")
            break
        except Exception as e:
            log(f"[!] CSRF attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(5)
                # Recreate session with cookies
                session = create_session(cookies)
    
    if not csrf:
        msg = "FATAL: Could not get CSRF token after 3 attempts. Cookies may be expired."
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

    # Check if streak already maintained today
    if user["hasFirstAndLastAnswered"] and not user["isStreakBroken"]:
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

    for code in all_codes[:MAX_ROOMS_TO_CHECK]:
        thm_code = code_to_thm(code)

        # Join room
        if not join_room(session, csrf, thm_code):
            continue

        # Get tasks
        tasks = get_tasks(session, csrf, thm_code)
        if not tasks:
            continue

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

                if data.get("isStreakIncreased"):
                    log(f"  [+] STREAK INCREASED! New: {data.get('currentStreak')}")
                    streak_increased = True
                    break
            else:
                msg = result.get("message", "unknown error")
                log(f"  [!] Wrong or error: {msg}")
                if "too fast" in str(msg).lower():
                    log(f"  [!] Rate limited, waiting 30s...")
                    time.sleep(30)

            time.sleep(ANSWER_DELAY)

        if streak_increased:
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
    send_telegram(msg)

    log(f"\n[+] Bot run completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
