import os
import sys
import datetime
from login import login_form
from keepstreak import keep_streak
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

print("UPDATED VERSION - USING DIRECT FIREFOX INITIALIZATION")

def main():
    # Configure Firefox options for GitHub Actions environment
    firefox_options = Options()
    firefox_options.headless = True
    firefox_options.add_argument("--no-sandbox")
    firefox_options.add_argument("--disable-dev-shm-usage")
    firefox_options.add_argument("--width=1920")
    firefox_options.add_argument("--height=1080")
    firefox_options.add_argument("--disable-gpu")
    firefox_options.add_argument("--disable-extensions")
    firefox_options.add_argument("--disable-infobars")
    firefox_options.set_preference("media.volume_scale", "0.0")
    firefox_options.set_preference("dom.push.enabled", False)
    firefox_options.set_preference("intl.accept_languages", "en-US, en")
    firefox_options.set_preference("dom.webnotifications.enabled", False)
    
    # Set MOZ_HEADLESS environment variable for GitHub Actions
    os.environ['MOZ_HEADLESS'] = '1'
    
    # Auto-detect Firefox binary path
    import shutil
    firefox_paths = [
        "/usr/bin/firefox",
        "/usr/bin/firefox-esr",
        "/snap/bin/firefox",
        "/usr/local/bin/firefox",
        shutil.which("firefox"),
        shutil.which("firefox-esr"),
    ]
    firefox_binary = None
    for path in firefox_paths:
        if path and os.path.isfile(path):
            firefox_binary = path
            break
    
    if firefox_binary:
        firefox_options.binary_location = firefox_binary
        print(f"[*] Firefox binary: {firefox_binary}")
    else:
        print("[!] WARNING: Firefox binary not found, Selenium will try auto-detect")
    
    try:
        # Configure the WebDriver with direct Firefox options
        driver = webdriver.Firefox(options=firefox_options)
        with open("tryhackmebot.log", 'a') as f:
            print("[+] Firefox driver initialized successfully")
            f.write("[+] Firefox driver initialized successfully\n")
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Error initializing Firefox webdriver: {e}")
            f.write(f"[!] Error initializing Firefox webdriver: {e}\n")
        sys.exit(1)
    
    # Set longer implicit wait time
    driver.implicitly_wait(20)
    
    # Clear terminal output
    os.system("cls" if sys.platform == "win32" else "clear")

    # Initialize log file
    with open("tryhackmebot.log", 'a') as f:
        print("[+] Starting...")
        date = datetime.datetime.now().strftime("%d-%m-%Y, %H:%M:%S")
        f.write(f"{date}\n")
        f.write("[+] Starting...\n")

    try:
        # Log in to TryHackMe
        login_form(driver)
        
        # Maintain the streak
        keep_streak(driver)
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Fatal error: {e}")
            f.write(f"[!] Fatal error: {e}\n")
    finally:
        # Ensure we always close the driver
        # Close the log file and quit the WebDriver
        with open("tryhackmebot.log", 'a') as f:
            print("[+] Closing...")
            f.write("[+] Closing...\n\n")
        
        driver.quit()


if __name__ == "__main__":
    main()
