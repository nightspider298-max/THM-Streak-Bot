#!/usr/bin/env python3
"""
THM Streak Bot - Maintains your TryHackMe daily streak
Uses nodriver (undetected Chrome) + capsolver for reCAPTCHA solving.
"""
import os
import sys
import json
import time
import datetime
import configparser

def log(msg):
    """Write to log file and print."""
    with open("tryhackmebot.log", 'a') as f:
        f.write(f"{msg}\n")
    print(msg)


def main():
    log("[+] Starting THM Streak Bot (nodriver + capsolver)")
    date = datetime.datetime.now().strftime("%d-%m-%Y, %H:%M:%S")
    log(f"{'='*50}")
    log(f"Bot run started at {date}")
    log(f"{'='*50}")

    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.action_chains import ActionChains
    except ImportError:
        log("[!] Missing dependency: pip install undetected-chromedriver")
        sys.exit(1)

    # Read config
    config = configparser.ConfigParser()
    config.read("account.conf")
    email = config["account"]["mail"]
    password = config["account"]["pass"]

    # Chrome options
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        log("[+] Launching Chrome...")
        driver = uc.Chrome(options=options, version_main=150)
        log("[+] Chrome started successfully")

        # Step 1: Login
        log("[+] Step 1: Logging in...")
        login_success = login(driver, email, password)
        
        if not login_success:
            log("[!] Login failed!")
            driver.save_screenshot("login_failed.png")
            return

        log("[+] Login successful!")

        # Step 2: Maintain streak
        log("[+] Step 2: Maintaining streak...")
        keep_streak(driver)

    except Exception as e:
        log(f"[!] Fatal error: {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        if driver:
            log("[+] Closing browser...")
            driver.quit()

    log(f"[+] Bot run completed at {datetime.datetime.now().strftime('%d-%m-%Y, %H:%M:%S')}")
    log(f"{'='*50}\n")


def login(driver, email, password, retry=0, max_retries=3):
    """Login to TryHackMe with reCAPTCHA solving."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time

    try:
        driver.get("https://tryhackme.com/login")
        time.sleep(5)

        title = driver.title
        log(f"[+] Page title: {title}")

        if "Vercel" in title:
            log("[!] Vercel checkpoint, waiting...")
            time.sleep(15)
            title = driver.title
            log(f"[+] After wait: {title}")

        # Fill form
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="usernameOrEmail"]'))
        )
        email_field.send_keys(email)
        time.sleep(0.5)

        pass_field = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
        pass_field.send_keys(password)
        time.sleep(0.5)
        log("[+] Credentials entered")

        # Submit
        driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        log("[+] Form submitted")
        time.sleep(5)

        # Check result
        current_url = driver.current_url
        log(f"[+] Current URL: {current_url}")

        if "dashboard" in current_url or "lobby" in current_url:
            return True

        # Check for reCAPTCHA challenge
        page_source = driver.page_source
        if "recaptcha" in page_source.lower() or "verify" in page_source.lower():
            log("[+] reCAPTCHA challenge detected, attempting to solve...")
            solved = solve_recaptcha(driver)
            if solved:
                time.sleep(5)
                current_url = driver.current_url
                if "dashboard" in current_url or "lobby" in current_url:
                    return True

        # Check for error messages
        if "incorrect" in page_source.lower() or "wrong" in page_source.lower():
            log("[!] Incorrect credentials")
            return False

        # Retry if needed
        if retry < max_retries:
            log(f"[+] Retrying login ({retry + 1}/{max_retries})...")
            time.sleep(5)
            return login(driver, email, password, retry + 1, max_retries)

        return False

    except Exception as e:
        log(f"[!] Login error: {e}")
        if retry < max_retries:
            return login(driver, email, password, retry + 1, max_retries)
        return False


def solve_recaptcha(driver):
    """Solve reCAPTCHA challenge using capsolver API."""
    from selenium.webdriver.common.by import By
    import time, json

    try:
        # Check if capsolver API key is available
        api_key = os.environ.get("CAPSOLVER_API_KEY", "")
        if not api_key:
            # Try reading from file
            try:
                with open("capsolver_key.txt", "r") as f:
                    api_key = f.read().strip()
            except:
                pass

        if not api_key:
            log("[!] No CAPSOLVER_API_KEY set, trying manual solve...")
            return solve_recaptcha_manual(driver)

        import capsolver
        capsolver.api_key = api_key

        # Find reCAPTCHA site key from page
        site_key = driver.execute_script("""
            var scripts = document.querySelectorAll('script[src*="recaptcha"]');
            for (var s of scripts) {
                var match = s.src.match(/render=([^&]+)/);
                if (match) return match[1];
            }
            return '6Lf2AcAsAAAAAPhhxmypzzqKtxPBw4yCzYxc6KhJ';
        """)
        log(f"[+] reCAPTCHA site key: {site_key}")

        # Create task
        task = {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": "https://tryhackme.com/login",
            "websiteKey": site_key,
        }

        log("[+] Solving reCAPTCHA with capsolver...")
        result = capsolver.solve(task)
        
        if result and result.get("solution"):
            token = result["solution"]["gRecaptchaResponse"]
            log(f"[+] CAPTCHA solved! Token length: {len(token)}")

            # Inject the token and submit
            driver.execute_script(f"""
                // Set the reCAPTCHA response
                document.getElementById('g-recaptcha-response').value = '{token}';
                
                // Also try to find hidden textarea
                var textareas = document.querySelectorAll('textarea[name="g-recaptcha-response"]');
                textareas.forEach(t => t.value = '{token}');
            """)

            # Find and click submit again
            submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
            submit.click()
            log("[+] Submitted with CAPTCHA token")
            time.sleep(10)

            current_url = driver.current_url
            log(f"[+] URL after CAPTCHA: {current_url}")
            return "dashboard" in current_url or "lobby" in current_url
        else:
            log("[!] CAPTCHA solving failed")
            return False

    except Exception as e:
        log(f"[!] CAPTCHA solving error: {e}")
        return False


def solve_recaptcha_manual(driver):
    """Manual reCAPTCHA solving - click checkbox and hope for the best."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    import time

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            if "recaptcha/api2/anchor" in src:
                driver.switch_to.frame(iframe)
                time.sleep(2)
                checkbox = driver.find_element(By.CSS_SELECTOR, '#recaptcha-anchor, [role="checkbox"]')
                ActionChains(driver).move_to_element(checkbox).pause(0.5).click().perform()
                driver.switch_to.default_content()
                log("[+] Clicked reCAPTCHA checkbox")
                time.sleep(10)

                # Check if we got image challenge
                iframes2 = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe2 in iframes2:
                    src2 = iframe2.get_attribute("src") or ""
                    if "recaptcha/api2/bframe" in src2:
                        driver.switch_to.frame(iframe2)
                        time.sleep(2)
                        # Check for image challenge
                        try:
                            challenge = driver.find_element(By.CSS_SELECTOR, '.rc-imageselect-desc-no-canonical')
                            log(f"[!] Image challenge appeared: {challenge.text}")
                            driver.switch_to.default_content()
                            return False
                        except:
                            driver.switch_to.default_content()
                            # Might have passed without challenge
                            return True

                return True

        return False
    except Exception as e:
        log(f"[!] Manual CAPTCHA error: {e}")
        try:
            driver.switch_to.default_content()
        except:
            pass
        return False


def keep_streak(driver):
    """Maintain the TryHackMe streak."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time, random

    try:
        # Navigate to polkit room
        time.sleep(random.uniform(2, 4))
        driver.get("https://tryhackme.com/room/polkit")
        time.sleep(5)
        log("[+] Navigated to polkit room")
        driver.save_screenshot("polkit_room.png")

        # Try to reset progress
        try:
            # Look for room settings / dropdown
            dropdowns = driver.find_elements(By.CSS_SELECTOR, 'div.dropdown, button.dropdown, [class*="dropdown"]')
            for dropdown in dropdowns:
                try:
                    dropdown.click()
                    time.sleep(1)
                    reset = driver.find_elements(By.XPATH, "//*[contains(text(), 'Reset')]")
                    for r in reset:
                        try:
                            r.click()
                            time.sleep(2)
                            # Confirm
                            confirm = driver.find_elements(By.XPATH, "//button[contains(text(), 'Yes')]")
                            for c in confirm:
                                c.click()
                                time.sleep(2)
                                log("[+] Room progress reset!")
                                break
                        except:
                            continue
                except:
                    continue
        except Exception as e:
            log(f"[!] Reset failed: {e}")

        # Try to complete a task
        time.sleep(random.uniform(2, 4))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        complete_btns = driver.find_elements(By.XPATH, 
            "//button[contains(text(), 'Complete')] | //button[contains(text(), 'Submit')] | //button[contains(text(), 'Answer')]")
        for btn in complete_btns:
            try:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    log("[+] Clicked complete button")
                    time.sleep(2)
                    break
            except:
                continue

        # Check streak
        time.sleep(2)
        driver.get("https://tryhackme.com/room/polkit")
        time.sleep(3)

        try:
            streak_el = driver.find_element(By.CSS_SELECTOR, '#user-streak, [data-streak], [class*="streak"]')
            streak = streak_el.get_attribute("data-streak") or streak_el.text
            log(f"[+] Streak: {streak}")
        except:
            log("[+] Could not find streak counter")

        log("[+] Streak maintenance completed!")

    except Exception as e:
        log(f"[!] Streak error: {e}")


if __name__ == "__main__":
    main()
