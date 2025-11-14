#!/usr/bin/env python3
"""Quick test to verify Chromium can access Amazon"""

from playwright.sync_api import sync_playwright

print("Testing Chromium access to Amazon...")
print("=" * 60)

try:
    with sync_playwright() as p:
        # Try Chrome first, fall back to Chromium
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
            "--disable-ipv6",  # Force IPv4
        ]

        try:
            print("1. Launching Google Chrome with IPv4 forced...")
            browser = p.chromium.launch(
                headless=True,
                channel="chrome",
                args=browser_args
            )
            print("   ✓ Using Google Chrome")
        except:
            print("1. Google Chrome not found, using Chromium...")
            browser = p.chromium.launch(
                headless=True,
                args=browser_args
            )
            print("   ✓ Using Chromium")

        page = browser.new_page()

        # Test Google first (should always work)
        print("2. Testing Google.com...")
        page.goto("https://www.google.com", timeout=15000)
        print(f"   ✓ Success! Title: {page.title()}")

        # Test Amazon (the problematic one)
        print("3. Testing Amazon.com...")
        try:
            page.goto("https://www.amazon.com", timeout=15000)
            print(f"   ✓ Success! Title: {page.title()}")

            # Test Amazon sign-in page
            print("4. Testing Amazon sign-in page...")
            page.goto("https://www.amazon.com/ap/signin", timeout=15000)
            print(f"   ✓ Success! Can access Amazon sign-in")

            print("\n" + "=" * 60)
            print("✓ ALL TESTS PASSED!")
            print("Your container can now access Amazon via Chromium")
            print("=" * 60)

        except Exception as e:
            print(f"   ✗ Failed to access Amazon: {e}")
            print("\n" + "=" * 60)
            print("✗ AMAZON ACCESS FAILED")
            print("=" * 60)
            print("\nPossible issues:")
            print("1. IPv6 not disabled - Run:")
            print("   sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1")
            print("2. IP address blocked by Amazon")
            print("3. Need to use proxy/VPN")
            raise

        browser.close()

except Exception as e:
    print(f"\n✗ Test failed: {e}")
    exit(1)

print("\nYou can now run the full automation!")
