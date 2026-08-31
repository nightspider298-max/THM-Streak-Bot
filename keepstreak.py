"""
Streak maintenance module for THM Streak Bot — Playwright version
Resets and completes an action in the polkit room to maintain daily streak.
"""
import asyncio
import random


def log(msg):
    """Write to log file and print."""
    with open("tryhackmebot.log", 'a') as f:
        f.write(f"{msg}\n")
    print(msg)


async def keep_streak(page, retry_count=0, max_retries=3):
    """Maintain the TryHackMe streak by resetting and completing a room task."""
    try:
        # Navigate to the polkit room
        await asyncio.sleep(random.uniform(2, 4))
        await page.goto("https://tryhackme.com/room/polkit", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)  # Let page fully load

        log("[+] Navigated to polkit room")
        await page.screenshot(path="polkit_room.png")

        # Step 1: Try to reset room progress
        await reset_room_progress(page)

        # Step 2: Complete a task (answer question or click complete)
        await asyncio.sleep(random.uniform(2, 4))
        await complete_task(page)

        # Step 3: Check streak counter
        await asyncio.sleep(random.uniform(2, 3))
        await page.goto("https://tryhackme.com/room/polkit", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        await check_streak(page)

        log("[+] Streak maintenance completed!")

    except Exception as e:
        log(f"[!] Streak maintenance error: {e}")
        if retry_count < max_retries:
            log(f"[+] Retrying ({retry_count + 1}/{max_retries})...")
            await asyncio.sleep(5)
            return await keep_streak(page, retry_count + 1, max_retries)
        log("[!] Max retries reached")


async def reset_room_progress(page):
    """Try to reset the room progress."""
    try:
        # Look for room menu / settings dropdown
        dropdown_selectors = [
            'div.dropdown',
            'button.dropdown',
            '[class*="dropdown"]',
            '[class*="menu"]',
            'button:has-text("⋮")',
            'button:has-text("...")',
        ]

        dropdown = None
        for selector in dropdown_selectors:
            try:
                dropdown = await page.wait_for_selector(selector, timeout=3000)
                if dropdown:
                    break
            except:
                continue

        if dropdown:
            await dropdown.click()
            await asyncio.sleep(1)

            # Look for reset option
            reset_selectors = [
                'a:has-text("Reset Room Progress")',
                'a:has-text("Reset")',
                'button:has-text("Reset")',
                'div:has-text("Reset Room Progress")',
            ]

            for selector in reset_selectors:
                try:
                    reset_btn = await page.wait_for_selector(selector, timeout=3000)
                    if reset_btn:
                        await reset_btn.click()
                        await asyncio.sleep(2)

                        # Confirm reset
                        confirm_selectors = [
                            'button:has-text("Yes")',
                            'button:has-text("Confirm")',
                            'button:has-text("OK")',
                        ]

                        for confirm_sel in confirm_selectors:
                            try:
                                confirm_btn = await page.wait_for_selector(confirm_sel, timeout=3000)
                                if confirm_btn:
                                    await confirm_btn.click()
                                    await asyncio.sleep(2)
                                    log("[+] Room progress reset!")
                                    return True
                            except:
                                continue
                except:
                    continue

        log("[!] Could not find reset option — room may already be reset or not started")
        return False

    except Exception as e:
        log(f"[!] Reset failed: {e}")
        return False


async def complete_task(page):
    """Try to complete a task in the room."""
    try:
        # Scroll to bottom to find task completion buttons
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)

        # Look for complete/submit buttons
        complete_selectors = [
            'button:has-text("Complete")',
            'button:has-text("Submit")',
            'button:has-text("Answer")',
            'button:has-text("Next")',
            'button:has-text("Mark Complete")',
            'button[class*="complete"]',
            'button[class*="submit"]',
        ]

        for selector in complete_selectors:
            try:
                btn = await page.wait_for_selector(selector, timeout=3000)
                if btn:
                    is_visible = await btn.is_visible()
                    is_enabled = await btn.is_enabled()
                    if is_visible and is_enabled:
                        await btn.click()
                        log(f"[+] Clicked: {selector}")
                        await asyncio.sleep(2)
                        return True
            except:
                continue

        # If no complete button found, try answering a question
        # Common THM room answers
        answer_selectors = [
            'input[type="text"]',
            'input[type="answer"]',
            'textarea',
        ]

        for selector in answer_selectors:
            try:
                answer_field = await page.query_selector(selector)
                if answer_field:
                    is_visible = await answer_field.is_visible()
                    if is_visible:
                        # Try common answers
                        for answer in ["polkit", "CVE-2021-4034", "yes", "true"]:
                            try:
                                await answer_field.fill(answer)
                                submit = await page.query_selector('button:has-text("Submit"), button[type="submit"]')
                                if submit:
                                    await submit.click()
                                    await asyncio.sleep(2)
                                    log(f"[+] Submitted answer: {answer}")
                                    return True
                            except:
                                continue
            except:
                continue

        log("[!] Could not find a task to complete")
        return False

    except Exception as e:
        log(f"[!] Task completion failed: {e}")
        return False


async def check_streak(page):
    """Check and log the current streak count."""
    try:
        # Look for streak counter
        streak_selectors = [
            '#user-streak',
            '[class*="streak"]',
            '[data-streak]',
            'div:has-text("streak")',
            'span:has-text("streak")',
        ]

        for selector in streak_selectors:
            try:
                streak_el = await page.query_selector(selector)
                if streak_el:
                    streak_text = await streak_el.text_content()
                    streak_count = await streak_el.get_attribute("data-streak")
                    if streak_count:
                        log(f"[+] Success! Your Streak is {streak_count}")
                        return streak_count
                    elif streak_text:
                        log(f"[+] Streak element text: {streak_text}")
                        return streak_text
            except:
                continue

        # Fallback: check page content
        content = await page.content()
        if "streak" in content.lower():
            log("[+] Streak mentioned on page (check manually)")
        else:
            log("[!] Could not find streak counter on page")

        return None

    except Exception as e:
        log(f"[!] Streak check failed: {e}")
        return None
