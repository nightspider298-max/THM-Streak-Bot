#!/usr/bin/env python3
"""
THM Streak Bot - Maintains your TryHackMe daily streak
"""
import os
import sys
import datetime
import subprocess
from login import login_form
from keepstreak import keep_streak
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service


def find_firefox_binary():
    """Find the real Firefox binary, preferring non-snap versions."""
    candidates = [
        "/usr/bin/firefox-esr",
        "/usr/bin/firefox",
        "/snap/bin/firefox",
        "/usr/local/bin/firefox",
    ]
    
    # Also check PATH
    for name in ["firefox-esr", "firefox"]:
        result = subprocess.run(["which", name], capture_output=True, text=True)
        if result.returncode == 0:
            path = result.stdout.strip()
            if path not in candidates:
                candidates.append(path)

    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            # Verify it's actually Firefox by checking --version
            try:
                result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and "firefox" in result.stdout.lower():
                    # Skip snap wrapper if real binary exists elsewhere
                    if path == "/usr/bin/firefox" and os.path.isfile("/usr/bin/firefox-esr"):
                        print(f"[*] Skipping snap wrapper: {path}")
                        continue
                    return path
            except (subprocess.TimeoutExpired, OSError):
                continue
    return None


def main():
    # Set MOZ_HEADLESS env var BEFORE anything else
    os.environ['MOZ_HEADLESS'] = '1'
    os.environ['MOZ_HEADLESS_WIDTH'] = '1920'
    os.environ['MOZ_HEADLESS_HEIGHT'] = '1080'

    print("[*] Detecting Firefox binary...")
    firefox_binary = find_firefox_binary()

    if firefox_binary:
        print(f"[+] Found Firefox: {firefox_binary}")
    else:
        print("[!] WARNING: Firefox binary not found via detection, Selenium will try auto-detect")

    # Configure Firefox options
    firefox_options = Options()
    firefox_options.headless = True
    firefox_options.add_argument("--no-sandbox")
    firefox_options.add_argument("--disable-dev-shm-usage")
    firefox_options.add_argument("--disable-gpu")
    firefox_options.add_argument("--disable-extensions")
    firefox_options.add_argument("--disable-infobars")
    firefox_options.add_argument("--width=1920")
    firefox_options.add_argument("--height=1080")

    # Set binary location if found
    if firefox_binary:
        firefox_options.binary_location = firefox_binary
        print(f"[*] Using Firefox binary: {firefox_binary}")

    # Find geckodriver
    geckodriver_path = subprocess.run(
        ["which", "geckodriver"], capture_output=True, text=True
    ).stdout.strip() or "/usr/local/bin/geckodriver"
    print(f"[*] Using geckodriver: {geckodriver_path}")

    service = Service(executable_path=geckodriver_path)

    try:
        driver = webdriver.Firefox(service=service, options=firefox_options)
        with open("tryhackmebot.log", 'a') as f:
            print("[+] Firefox driver initialized successfully")
            f.write(f"[+] Firefox driver initialized successfully\n")
            f.write(f"    Binary: {firefox_binary}\n")
            f.write(f"    Geckodriver: {geckodriver_path}\n")
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Error initializing Firefox webdriver: {e}")
            f.write(f"[!] Error initializing Firefox webdriver: {e}\n")
            # Log environment details for debugging
            f.write(f"    Firefox binary: {firefox_binary}\n")
            f.write(f"    Geckodriver: {geckodriver_path}\n")
            f.write(f"    DISPLAY: {os.environ.get('DISPLAY', 'not set')}\n")
        sys.exit(1)

    # Set longer implicit wait time
    driver.implicitly_wait(20)

    # Clear terminal output
    os.system("cls" if sys.platform == "win32" else "clear")

    # Initialize log file
    with open("tryhackmebot.log", 'a') as f:
        print("[+] Starting...")
        date = datetime.datetime.now().strftime("%d-%m-%Y, %H:%M:%S")
        f.write(f"\n{'='*50}\n")
        f.write(f"Bot run started at {date}\n")
        f.write(f"{'='*50}\n")

    try:
        login_form(driver)
        keep_streak(driver)
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Fatal error: {e}")
            f.write(f"[!] Fatal error: {e}\n")
    finally:
        with open("tryhackmebot.log", 'a') as f:
            print("[+] Closing...")
            f.write(f"[+] Closing...\n\n")
        driver.quit()


if __name__ == "__main__":
    main()
