#!/usr/bin/env python3
"""
THM Streak Bot - Maintains your TryHackMe daily streak
Uses Playwright (built-in Firefox) to bypass Vercel Security Checkpoint.
"""
import os
import sys
import datetime
import configparser
import asyncio
from playwright.async_api import async_playwright

# Import login and streak modules
from login import login_form
from keepstreak import keep_streak


def log(msg, also_print=True):
    """Write to log file and optionally print."""
    with open("tryhackmebot.log", 'a') as f:
        f.write(f"{msg}\n")
    if also_print:
        print(msg)


async def main():
    log("[+] Starting THM Streak Bot (Playwright + Firefox)")
    date = datetime.datetime.now().strftime("%d-%m-%Y, %H:%M:%S")
    log(f"{'='*50}")
    log(f"Bot run started at {date}")
    log(f"{'='*50}")

    async with async_playwright() as p:
        # Launch Firefox (Playwright's own binary — no system Firefox needed)
        browser = await p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "media.volume_scale": "0.0",
                "dom.webnotifications.enabled": False,
                "intl.accept_languages": "en-US, en",
            }
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        page = await context.new_page()

        try:
            # Step 1: Login
            log("[+] Step 1: Logging in to TryHackMe...")
            await login_form(page)

            # Step 2: Maintain streak
            log("[+] Step 2: Maintaining streak...")
            await keep_streak(page)

        except Exception as e:
            log(f"[!] Fatal error: {e}")
        finally:
            log("[+] Closing browser...")
            await browser.close()

    log(f"[+] Bot run completed at {datetime.datetime.now().strftime('%d-%m-%Y, %H:%M:%S')}")
    log(f"{'='*50}\n")


if __name__ == "__main__":
    asyncio.run(main())
