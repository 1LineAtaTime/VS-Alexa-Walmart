"""Launch browser with persistent profile for manual login.

Usage: python manual_login.py
Opens Chrome with the shared persistent profile so you can manually log into Walmart.
The session will persist for the automation to use afterwards.
Press Enter in the terminal when done logging in.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

profile_dir = Path("credentials/.playwright_profile")
profile_dir.mkdir(parents=True, exist_ok=True)

print(f"Launching Chrome with persistent profile: {profile_dir}")
print("Log into Walmart manually, then press Enter here when done.")
print()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        channel="chrome",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--window-size=1920,1080",
            "--start-maximized",
        ]
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://www.walmart.com/account")
    print("Browser is open. Navigate to Walmart and log in.")
    print("Close the browser window when you're done (or Ctrl+C here).")
    try:
        # Wait until all pages are closed (user closes the browser)
        page.wait_for_event("close", timeout=600000)  # 10 min max
    except Exception:
        pass
    print("Session saved to persistent profile.")
    context.close()
