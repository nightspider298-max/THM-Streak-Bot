#!/usr/bin/env python3
"""
Telegram Bot Listener for THM Streak Bot
Handles /logs command to fetch latest workflow run logs.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import zipfile
import io

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "nightspider298-max/THM-Streak-Bot")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
POLL_INTERVAL = 3  # seconds

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
GH_API = "https://api.github.com"


def send_message(text, parse_mode="Markdown"):
    """Send a message to the configured Telegram chat."""
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode
    }).encode()
    req = urllib.request.Request(f"{API_BASE}/sendMessage", data=data)
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"[!] Failed to send message: {e}")


def send_chat_action(action="typing"):
    """Show bot is typing."""
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "action": action
    }).encode()
    req = urllib.request.Request(f"{API_BASE}/sendChatAction", data=data)
    try:
        urllib.request.urlopen(req)
    except:
        pass


def get_updates(offset=None):
    """Get pending Telegram updates."""
    url = f"{API_BASE}/getUpdates?timeout=5"
    if offset:
        url += f"&offset={offset}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except Exception as e:
        print(f"[!] Error getting updates: {e}")
        return {"result": []}


def get_latest_run():
    """Get the latest workflow run from GitHub."""
    url = f"{GH_API}/repos/{REPO}/actions/runs?per_page=1&status=completed"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        if data.get("workflow_runs"):
            return data["workflow_runs"][0]
    except Exception as e:
        print(f"[!] Error fetching run: {e}")
    return None


def get_run_logs(run_id):
    """Download and extract logs from a workflow run."""
    url = f"{GH_API}/repos/{REPO}/actions/runs/{run_id}/logs"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        resp = urllib.request.urlopen(req)
        zip_data = resp.read()
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            logs = ""
            for name in zf.namelist():
                if name.endswith(".txt"):
                    content = zf.read(name).decode("utf-8", errors="replace")
                    # Get last 100 lines of each log
                    lines = content.strip().split("\n")
                    if len(lines) > 100:
                        lines = ["... (truncated) ..."] + lines[-100:]
                    logs += f"\n📄 *{name.split('/')[-1]}*\n"
                    logs += "\n".join(lines)
                    logs += "\n"
            return logs
    except Exception as e:
        return f"Error fetching logs: {e}"


def handle_logs_command():
    """Handle the /logs command - fetch and send latest run logs."""
    send_chat_action("typing")
    send_message("⏳ Fetching latest run logs...")
    
    run = get_latest_run()
    if not run:
        send_message("❌ No completed runs found.")
        return
    
    # Build status message
    status = run.get("conclusion", "unknown")
    emoji = "✅" if status == "success" else "❌"
    run_number = run.get("run_number", "?")
    created = run.get("created_at", "unknown")
    run_url = run.get("html_url", "")
    workflow = run.get("name", "unknown")
    
    header = f"{emoji} *Latest Run #{run_number}*\n"
    header += f"📋 *Workflow:* {workflow}\n"
    header += f"📊 *Status:* {status}\n"
    header += f"🕐 *Time:* {created}\n"
    header += f"🔗 [View Run]({run_url})\n"
    
    send_message(header)
    
    # Fetch and send logs
    send_chat_action("typing")
    logs = get_run_logs(run["id"])
    
    if logs:
        # Telegram message limit is 4096 chars
        if len(logs) > 4000:
            # Send in chunks
            chunks = [logs[i:i+4000] for i in range(0, len(logs), 4000)]
            for i, chunk in enumerate(chunks):
                send_message(f"📄 *Logs (part {i+1}/{len(chunks)})*\n```\n{chunk}\n```")
        else:
            send_message(f"📄 *Logs*\n```\n{logs}\n```")
    else:
        send_message("📄 No log content available.")


def trigger_streak_bot(force_new=False, complete_room=None, complete_random=False):
    """Trigger the streak bot workflow via GitHub API."""
    url = f"{GH_API}/repos/{REPO}/actions/workflows/thmbot.yml/dispatches"
    payload = {"ref": "main"}
    inputs = {}
    if force_new:
        inputs["force_new"] = "true"
    if complete_room:
        inputs["complete_room"] = complete_room
    if complete_random:
        inputs["complete_random"] = "true"
    if inputs:
        payload["inputs"] = inputs
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"token {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        resp = urllib.request.urlopen(req)
        print(f"[+] Workflow triggered successfully (status={resp.status})")
        return resp.status == 204
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"[!] Error triggering workflow: {e.code} {e.reason}")
        print(f"[!] Response: {body[:200]}")
        send_message(f"❌ Failed to trigger bot: HTTP {e.code}\n{body[:100]}")
        return False
    except Exception as e:
        print(f"[!] Error triggering workflow: {e}")
        send_message(f"❌ Failed to trigger bot: {e}")
        return False


def get_workflow_runs_active():
    """Check if there's already a running workflow."""
    url = f"{GH_API}/repos/{REPO}/actions/runs?per_page=5&status=in_progress"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {GH_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        for run in data.get("workflow_runs", []):
            name = run.get("name", "")
            # Check for thmbot workflow by name or path
            if "streak" in name.lower() or "thmbot" in name.lower():
                return True
    except:
        pass
    return False


def handle_now_command():
    """Handle /now command - run streak bot immediately."""
    send_chat_action("typing")
    
    # Check if already running
    if get_workflow_runs_active():
        send_message("⚠️ Streak bot is already running! Wait for it to finish.")
        return
    
    send_message("🚀 *Triggering streak bot now...*\n\nThis takes ~2-3 minutes. You'll get a notification when done.")
    
    if trigger_streak_bot():
        print("[+] Streak bot triggered successfully")
    else:
        send_message("❌ Failed to trigger streak bot. Check GitHub Actions.")


def handle_new_command():
    """Handle /new command - solve a brand new challenge."""
    send_chat_action("typing")
    
    # Check if already running
    if get_workflow_runs_active():
        send_message("⚠️ Streak bot is already running! Wait for it to finish.")
        return
    
    send_message("🎯 *Solving a NEW challenge...*\n\nFetching a fresh room from the writeup repo. Takes ~2-3 minutes.")
    
    if trigger_streak_bot(force_new=True):
        print("[+] New challenge triggered successfully")
    else:
        send_message("❌ Failed to trigger. Check GitHub Actions.")


def handle_complete_command(room_name):
    """Handle /complete [room] command - solve ALL questions in a room.
    If no room specified, picks a random uncompleted room."""
    send_chat_action("typing")
    
    # Check if already running
    if get_workflow_runs_active():
        send_message("⚠️ Streak bot is already running! Wait for it to finish.")
        return
    
    if room_name:
        room_slug = room_name.lower().strip().replace(" ", "-")
        send_message(f"Completing room: *{room_slug}*\n\nSolving ALL questions. This may take a few minutes.")
        if trigger_streak_bot(complete_room=room_slug):
            print(f"[+] Complete room triggered: {room_slug}")
        else:
            send_message("❌ Failed to trigger. Check GitHub Actions.")
    else:
        send_message("🎲 *Random room mode*\n\nPicking a random uncompleted room and solving ALL questions.")
        if trigger_streak_bot(complete_random=True):
            print("[+] Complete random triggered")
        else:
            send_message("❌ Failed to trigger. Check GitHub Actions.")


def handle_start_command():
    """Handle /start command."""
    send_message(
        "👻 *THM Streak Bot*\n\n"
        "Commands:\n"
        "/now — Run streak bot (maintain streak)\n"
        "/new — Solve a brand NEW challenge\n"
        "/complete — Solve ALL questions in a random uncompleted room\n"
        "/complete <room> — Solve ALL questions in a specific room\n"
        "/logs — Get latest run logs\n"
        "/status — Check bot status\n"
        "/help — Show this help"
    )


def handle_status_command():
    """Handle /status command."""
    run = get_latest_run()
    if run:
        status = run.get("conclusion", "unknown")
        emoji = "✅" if status == "success" else "❌"
        created = run.get("created_at", "unknown")
        send_message(f"{emoji} *Bot Status: Running*\nLast run: {created}\nStatus: {status}")
    else:
        send_message("⚠️ *Bot Status: No runs found*")


def main():
    print(f"[*] Telegram listener started for {REPO}")
    print(f"[*] Polling every {POLL_INTERVAL}s...")
    
    offset = None
    
    while True:
        try:
            updates = get_updates(offset)
            
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                
                message = update.get("message", {})
                text = message.get("text", "").strip().lower()
                chat_id = str(message.get("chat", {}).get("id", ""))
                
                # Only respond to our configured chat
                if chat_id != CHAT_ID:
                    continue
                
                print(f"[+] Received: {text}")
                
                if text == "/logs":
                    handle_logs_command()
                elif text == "/now":
                    handle_now_command()
                elif text == "/new":
                    handle_new_command()
                elif text.startswith("/complete"):
                    # Extract room name after /complete
                    parts = text.split(maxsplit=1)
                    room = parts[1] if len(parts) > 1 else ""
                    handle_complete_command(room)
                elif text == "/start":
                    handle_start_command()
                elif text == "/status":
                    handle_status_command()
                elif text == "/help":
                    handle_start_command()
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n[*] Listener stopped")
            break
        except Exception as e:
            print(f"[!] Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
