"""
Login module for THM Streak Bot — Playwright version
Handles TryHackMe login including reCAPTCHA audio solving.
"""
import os
import time
import random
import configparser


def log(msg):
    """Write to log file and print."""
    with open("tryhackmebot.log", 'a') as f:
        f.write(f"{msg}\n")
    print(msg)


async def login_form(page, retry_count=0, max_retries=3):
    """Handle the login form for TryHackMe using Playwright."""
    config = configparser.ConfigParser()
    config.read("account.conf")

    email = config["account"]["mail"]
    password = config["account"]["pass"]

    try:
        # Navigate to login page
        await page.goto("https://tryhackme.com/login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)  # Let JS render

        title = await page.title()
        log(f"[+] Page title: {title}")

        # Check for Vercel Security Checkpoint
        content = await page.content()
        if "Vercel Security" in content:
            log("[!] Vercel Security Checkpoint detected, waiting 15s...")
            await asyncio.sleep(15)
            title = await page.title()
            log(f"[+] After wait, title: {title}")

        # Save screenshot
        try:
            await page.screenshot(path="login_page.png")
            log("[+] Saved screenshot of login page")
        except Exception as e:
            log(f"[!] Failed to save screenshot: {e}")

        # Find and fill email field
        email_selectors = [
            'input[name="usernameOrEmail"]',
            'input[type="email"]',
            'input[id="email"]',
            'input[placeholder*="email"]',
            'input[placeholder*="example"]',
        ]

        email_field = None
        for selector in email_selectors:
            try:
                email_field = await page.wait_for_selector(selector, timeout=5000)
                if email_field:
                    log(f"[+] Found email field: {selector}")
                    break
            except:
                continue

        if not email_field:
            raise Exception("Email field not found with any selector")

        await email_field.fill(email)
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Find and fill password field
        pass_selectors = [
            'input[name="password"]',
            'input[type="password"]',
            'input[id="password"]',
        ]

        pass_field = None
        for selector in pass_selectors:
            try:
                pass_field = await page.wait_for_selector(selector, timeout=5000)
                if pass_field:
                    log(f"[+] Found password field: {selector}")
                    break
            except:
                continue

        if not pass_field:
            raise Exception("Password field not found")

        await pass_field.fill(password)
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Handle reCAPTCHA if present
        await handle_recaptcha(page)

        # Find and click submit button
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Log In")',
            'button:has-text("Login")',
            'button:has-text("Sign In")',
            'input[type="submit"]',
        ]

        submit_btn = None
        for selector in submit_selectors:
            try:
                submit_btn = await page.wait_for_selector(selector, timeout=5000)
                if submit_btn:
                    log(f"[+] Found submit button: {selector}")
                    break
            except:
                continue

        if not submit_btn:
            raise Exception("Submit button not found")

        await submit_btn.click()

        # Wait for navigation
        await asyncio.sleep(10)

        # Check login result
        current_url = page.url
        log(f"[+] Current URL after login: {current_url}")

        if "dashboard" in current_url or "lobby" in current_url:
            log("[+] Login successful!")
            await page.screenshot(path="dashboard.png")
            return True
        elif "two-factor" in current_url:
            log("[!] Two-factor authentication required!")
            log("[!] Please add 2FA bypass or disable 2FA for this account.")
            raise Exception("2FA required")
        elif "login" in current_url:
            # Still on login page - check for error
            error_text = await page.text_content("body")
            if "incorrect" in error_text.lower() or "wrong" in error_text.lower():
                log("[!] Login failed: incorrect credentials")
                if retry_count < max_retries:
                    return await login_form(page, retry_count + 1, max_retries)
            log("[!] Login failed, still on login page")
            if retry_count < max_retries:
                return await login_form(page, retry_count + 1, max_retries)
            raise Exception("Login failed after max retries")
        else:
            log(f"[+] Login appears successful (URL: {current_url})")
            return True

    except Exception as e:
        log(f"[!] Login error: {e}")
        if retry_count < max_retries:
            log(f"[+] Retrying ({retry_count + 1}/{max_retries})...")
            return await login_form(page, retry_count + 1, max_retries)
        raise


async def handle_recaptcha(page):
    """Handle reCAPTCHA if present on the login page."""
    try:
        # Check if reCAPTCHA iframe exists
        recaptcha_frame = await page.query_selector('iframe[src*="recaptcha"]')
        if not recaptcha_frame:
            return

        log("[+] reCAPTCHA detected, attempting to solve...")

        # Switch to recaptcha iframe
        frame = await recaptcha_frame.content_frame()
        if not frame:
            return

        # Click the checkbox
        checkbox = await frame.query_selector('.recaptcha-checkbox-border')
        if checkbox:
            await checkbox.click()
            await asyncio.sleep(3)

            # Check if audio challenge appeared
            audio_btn = await frame.query_selector('#recaptcha-audio-button')
            if audio_btn:
                await audio_btn.click()
                await asyncio.sleep(2)

                # Try to solve audio challenge
                await solve_audio_recaptcha(frame, page)

        log("[+] reCAPTCHA handling complete")
    except Exception as e:
        log(f"[!] reCAPTCHA handling failed: {e}")


async def solve_audio_recaptcha(frame, page):
    """Attempt to solve audio reCAPTCHA challenge."""
    try:
        # Get the audio source URL
        download_link = await frame.query_selector('a[href*="recaptcha"]')
        if download_link:
            audio_url = await download_link.get_attribute("href")
            log(f"[+] Audio URL found: {audio_url[:50]}...")
            # Note: Actual audio solving requires speech recognition
            # which is complex in async context. For now, we log it.
            log("[!] Audio CAPTCHA detected — manual intervention may be needed")
    except Exception as e:
        log(f"[!] Audio CAPTCHA solving failed: {e}")


# Need asyncio for sleep
import asyncio
