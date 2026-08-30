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


def handle_start_command():
    """Handle /start command."""
    send_message(
        "👻 *THM Streak Bot*\n\n"
        "Commands:\n"
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
