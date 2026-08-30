import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException


def keep_streak(driver, retry_count=0, max_retries=3):
    """Maintain the TryHackMe streak by resetting and completing an action in the polkit room"""
    try:
        # Navigate to the polkit room
        time.sleep(random.uniform(3, 6))
        driver.get("https://tryhackme.com/room/polkit")
        
        with open("tryhackmebot.log", 'a') as f:
            print("[+] Navigated to polkit room")
            f.write("[+] Navigated to polkit room\n")
        
        # Try to find and click the profile dropdown
        try:
            dropdown = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'dropdown')]"))
            )
            dropdown.click()
            
            time.sleep(random.uniform(1, 2))
            
            # Find and click the reset progress option
            reset_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Reset Room Progress')]"))
            )
            reset_option.click()
            
            time.sleep(random.uniform(1, 3))
            
            # Confirm reset
            confirm_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Yes')]"))
            )
            confirm_button.click()
            
            with open("tryhackmebot.log", 'a') as f:
                print("[+] Room's Progress Reset")
                f.write("[+] Room's Progress Reset\n")
                
        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException) as e:
            with open("tryhackmebot.log", 'a') as f:
                print(f"[!] Error resetting progress: {e}")
                f.write(f"[!] Error resetting progress: {e}\n")
                print("[!] Trying alternative XPaths...")
                f.write("[!] Trying alternative XPaths...\n")
            
            # Try alternative XPaths
            try:
                # Try to find any dropdown or menu button
                dropdown_alternatives = [
                    "//div[contains(@class, 'dropdown')]",
                    "//button[contains(@class, 'dropdown')]",
                    "//div[contains(@class, 'menu')]",
                    "//button[contains(@class, 'menu')]",
                    "//div[@id='user-menu']",
                    "//button[contains(@class, 'navbar-toggler')]"
                ]
                
                for xpath in dropdown_alternatives:
                    try:
                        menu = driver.find_element(By.XPATH, xpath)
                        menu.click()
                        time.sleep(1)
                        break
                    except:
                        continue
                
                # Look for reset option with various XPaths
                reset_alternatives = [
                    "//a[contains(text(), 'Reset')]",
                    "//a[contains(text(), 'reset')]",
                    "//button[contains(text(), 'Reset')]",
                    "//div[contains(text(), 'Reset')]",
                    "//span[contains(text(), 'Reset')]"
                ]
                
                for xpath in reset_alternatives:
                    try:
                        reset = driver.find_element(By.XPATH, xpath)
                        reset.click()
                        time.sleep(1)
                        break
                    except:
                        continue
                
                # Try to find confirm button with various XPaths
                confirm_alternatives = [
                    "//button[contains(text(), 'Yes')]",
                    "//button[contains(text(), 'Confirm')]",
                    "//button[contains(text(), 'OK')]",
                    "//button[contains(@class, 'confirm')]",
                    "//button[contains(@class, 'success')]"
                ]
                
                for xpath in confirm_alternatives:
                    try:
                        confirm = driver.find_element(By.XPATH, xpath)
                        confirm.click()
                        break
                    except:
                        continue
                        
            except Exception as e2:
                with open("tryhackmebot.log", 'a') as f:
                    print(f"[!] Alternative methods also failed: {e2}")
                    f.write(f"[!] Alternative methods also failed: {e2}\n")

        # Scroll to the bottom and complete an action
        time.sleep(random.uniform(3, 6))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(random.uniform(2, 3))
        
        # Try to find and click a complete button
        try:
            complete_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Complete')]"))
            )
            complete_button.click()
        except (NoSuchElementException, TimeoutException) as e:
            with open("tryhackmebot.log", 'a') as f:
                print(f"[!] Could not find complete button: {e}")
                f.write(f"[!] Could not find complete button: {e}\n")
                print("[!] Trying alternative buttons...")
                f.write("[!] Trying alternative buttons...\n")
            
            # Try alternative buttons
            button_alternatives = [
                "//button[contains(@class, 'completed')]",
                "//button[contains(@class, 'complete')]",
                "//button[contains(@class, 'submit')]",
                "//button[contains(@class, 'answer')]",
                "//button[contains(text(), 'Submit')]",
                "//button[contains(text(), 'Answer')]",
                "//button[contains(text(), 'Next')]"
            ]
            
            for xpath in button_alternatives:
                try:
                    button = driver.find_element(By.XPATH, xpath)
                    button.click()
                    break
                except:
                    continue

        # Check the streak counter
        time.sleep(random.uniform(1, 3))
        driver.get("https://tryhackme.com/room/polkit")  # Refresh to see updated streak
        
        try:
            streak = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "user-streak"))
            ).get_attribute("data-streak")
            
            with open("tryhackmebot.log", 'a') as f:
                print(f"[+] Success! Your Streak is {streak}")
                f.write(f"[+] Success! Your Streak is {streak}\n")
                
        except (NoSuchElementException, TimeoutException) as e:
            with open("tryhackmebot.log", 'a') as f:
                print(f"[!] Could not find streak counter: {e}")
                f.write(f"[!] Could not find streak counter: {e}\n")
                
            # Try to find streak counter with alternative XPaths
            streak_alternatives = [
                "//div[contains(@class, 'streak')]",
                "//span[contains(@class, 'streak')]",
                "//div[contains(text(), 'streak')]",
                "//span[contains(text(), 'streak')]"
            ]
            
            for xpath in streak_alternatives:
                try:
                    streak_element = driver.find_element(By.XPATH, xpath)
                    with open("tryhackmebot.log", 'a') as f:
                        print(f"[+] Found streak element: {streak_element.text}")
                        f.write(f"[+] Found streak element: {streak_element.text}\n")
                    break
                except:
                    continue
            
    except KeyboardInterrupt:
        with open("tryhackmebot.log", 'a') as f:
            print("[!] Process interrupted by user")
            f.write("[!] Process interrupted by user\n")
        pass
            
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Something Went Wrong: {e}")
            f.write(f"[!] Something Went Wrong: {e}\n")
        if retry_count < max_retries:
            print(f"[+] Trying again ({retry_count + 1}/{max_retries})...")
            with open("tryhackmebot.log", 'a') as f:
                f.write(f"[+] Trying again ({retry_count + 1}/{max_retries})...\n")
            keep_streak(driver, retry_count + 1, max_retries)
        else:
            with open("tryhackmebot.log", 'a') as f:
                print("[!] Max streak retries reached, exiting")
                f.write("[!] Max streak retries reached, exiting\n")
