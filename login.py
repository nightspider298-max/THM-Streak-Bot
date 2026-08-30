import os
import time
import random
import configparser
from urllib import request
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementNotInteractableException, NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pydub
import speech_recognition


def change_type():
    """Convert audio from mp3 to wav format for speech recognition"""
    try:
        sound = pydub.AudioSegment.from_mp3(f"{os.getcwd()}/recapchasound/sample.wav")
        sound.export(f"{os.getcwd()}/recapchasound/sample.wav", format="wav")
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Error converting audio: {e}")
            f.write(f"[!] Error converting audio: {e}\n")


def recapcha(driver):
    """Solve reCAPTCHA challenge using audio recognition"""
    time.sleep(random.uniform(1,3))
    with open("tryhackmebot.log", 'a') as f:
        print("[+] Attempting to Solve Recaptcha")
        f.write("[+] Attempting to Solve Recaptcha\n")

    try:
        # Find and switch to the reCAPTCHA iframe
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in frames:
            if "recaptcha" in frame.get_attribute("src").lower():
                driver.switch_to.frame(frame)
                break
        
        time.sleep(random.uniform(1,3))
        driver.find_element(By.CLASS_NAME, "recaptcha-checkbox-border").click()
        
        time.sleep(random.uniform(1,3))
        driver.switch_to.default_content()
        
        # Switch to the audio challenge
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            for frame in frames:
                if "recaptcha" in frame.get_attribute("src").lower() and "challenge" in frame.get_attribute("src").lower():
                    driver.switch_to.frame(frame)
                    break
            
            # Click the audio button
            audio_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "recaptcha-audio-button"))
            )
            audio_button.click()

            time.sleep(random.uniform(1,3))
            
            # Click the play button
            play_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[starts-with(@class, 'rc-button')]"))
            )
            play_button.click()

            time.sleep(random.uniform(1,3))
            
            # Get the audio source
            src = driver.find_element(By.XPATH, "//a[contains(text(), 'Download')]").get_attribute("href")
            os.makedirs("recapchasound", exist_ok=True)
            request.urlretrieve(src, f"{os.getcwd()}/recapchasound/sample.wav")
            change_type()

            # Use speech recognition to solve the CAPTCHA
            sample_audio = speech_recognition.AudioFile(f"{os.getcwd()}/recapchasound/sample.wav")
            recognize = speech_recognition.Recognizer()
            with sample_audio as source:
                audio = recognize.record(source)
            
            key = recognize.recognize_google(audio)
            with open("tryhackmebot.log", 'a') as f:
                print(f"[+] Recaptcha solved successfully")
                f.write(f"[+] Recaptcha solved successfully\n")

            # Input the recognized text
            driver.find_element(By.ID, "audio-response").send_keys(key.lower())
            time.sleep(random.uniform(1,3))
            driver.find_element(By.ID, "recaptcha-verify-button").click()
            
        except (ElementNotInteractableException, NoSuchElementException, TimeoutException) as e:
            with open("tryhackmebot.log", 'a') as f:
                print(f"[!] Error with reCAPTCHA challenge: {e}")
                f.write(f"[!] Error with reCAPTCHA challenge: {e}\n")
            pass
        
    except Exception as e:
        with open("tryhackmebot.log", 'a') as f:
            print(f"[!] Error solving reCAPTCHA: {e}")
            f.write(f"[!] Error solving reCAPTCHA: {e}\n")
    
    # Return to main content
    driver.switch_to.default_content()


def login_form(driver, retry_count=0, max_retries=3):
    """Handle the login form for TryHackMe"""
    config = configparser.ConfigParser()
    config.read("account.conf")
    try:
        # Take a screenshot before interacting with the page
        driver.get("https://tryhackme.com/login")
        time.sleep(5)  # Give page time to fully load
        
        try:
            driver.save_screenshot("login_page.png")
            with open("tryhackmebot.log", 'a') as f:
                print("[+] Saved screenshot of login page")
                f.write("[+] Saved screenshot of login page\n")
        except Exception as e:
            with open("tryhackmebot.log", 'a') as f:
                print(f"[!] Failed to save screenshot: {e}")
                f.write(f"[!] Failed to save screenshot: {e}\n")
        
        # Debug - Print page source
        with open("tryhackmebot.log", 'a') as f:
            print(f"[+] Page title: {driver.title}")
            f.write(f"[+] Page title: {driver.title}\n")
        
        # Enhanced error handling for finding elements with multiple selectors
        # Try different selectors for email field
        email_selectors = [
            (By.ID, "email"),
            (By.NAME, "email"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[contains(@placeholder, 'email')]"),
            (By.XPATH, "//input[contains(@class, 'form-control')]")
        ]
        
        email_field = None
        for selector_type, selector_value in email_selectors:
            try:
                email_field = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                with open("tryhackmebot.log", 'a') as f:
                    print(f"[+] Found email field with selector: {selector_type}={selector_value}")
                    f.write(f"[+] Found email field with selector: {selector_type}={selector_value}\n")
                break
            except:
                continue
        
        if not email_field:
            raise Exception("Email field not found with any selector")
        
        email_field.clear()
        email_field.send_keys(config["account"]["mail"])
        time.sleep(random.uniform(1,2))
        
        # Try different selectors for password field
        password_selectors = [
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.XPATH, "//input[@type='password']"),
            (By.XPATH, "//input[contains(@placeholder, 'password')]")
        ]
        
        password_field = None
        for selector_type, selector_value in password_selectors:
            try:
                password_field = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                with open("tryhackmebot.log", 'a') as f:
                    print(f"[+] Found password field with selector: {selector_type}={selector_value}")
                    f.write(f"[+] Found password field with selector: {selector_type}={selector_value}\n")
                break
            except:
                continue
        
        if not password_field:
            raise Exception("Password field not found with any selector")
        
        password_field.clear()
        password_field.send_keys(config["account"]["pass"])
        
        # Handle reCAPTCHA
        recapcha(driver)
        
        time.sleep(random.uniform(1,2))
        
        # Try different selectors for login button
        button_selectors = [
            (By.XPATH, "//button[contains(text(), 'Sign In')]"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//input[@type='submit']"),
            (By.XPATH, "//button[contains(@class, 'btn')]")
        ]
        
        login_button = None
        for selector_type, selector_value in button_selectors:
            try:
                login_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                with open("tryhackmebot.log", 'a') as f:
                    print(f"[+] Found login button with selector: {selector_type}={selector_value}")
                    f.write(f"[+] Found login button with selector: {selector_type}={selector_value}\n")
                break
            except:
                continue
        
        if not login_button:
            raise Exception("Login button not found with any selector")
        
        login_button.click()
        
        # Verify successful login with longer wait time
        time.sleep(10)  # Increased wait time for login
        with open("tryhackmebot.log", 'a') as f:
            print(f"[+] Current URL after login attempt: {driver.current_url}")
            f.write(f"[+] Current URL after login attempt: {driver.current_url}\n")
            
        if "dashboard" in driver.current_url or "profile" in driver.current_url:
            with open("tryhackmebot.log", 'a') as f:
                print("[+] You Are Logged In!")
                f.write("[+] You Are Logged In!\n")
        else:
            with open("tryhackmebot.log", 'a') as f:
                print("[!] Login failed, current URL doesn't indicate success")
                f.write("[!] Login failed, current URL doesn't indicate success\n")
            if retry_count < max_retries:
                login_form(driver, retry_count + 1, max_retries)
            else:
                with open("tryhackmebot.log", 'a') as f:
                    print("[!] Max login retries reached")
                    f.write("[!] Max login retries reached\n")
            
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
            login_form(driver, retry_count + 1, max_retries)
        else:
            with open("tryhackmebot.log", 'a') as f:
                print("[!] Max login retries reached, exiting")
                f.write("[!] Max login retries reached, exiting\n")
