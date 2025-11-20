"""Test Home Assistant notification setup."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.notifications import HomeAssistantNotifier

def test_connection():
    """Test Home Assistant connection."""
    print("="*60)
    print("Testing Home Assistant Connection")
    print("="*60)

    notifier = HomeAssistantNotifier()

    if not notifier.enabled:
        print("\n[X] Home Assistant notifications are NOT enabled")
        print("Please check your credentials/credentials.py configuration")
        return False

    print(f"\n[OK] Configuration loaded:")
    print(f"  URL: {notifier.ha_url}")
    print(f"  Entity: {notifier.alexa_entity}")
    print(f"  Token: {notifier.ha_token[:20]}..." if notifier.ha_token else "  Token: Not set")

    print("\n1. Testing connection to Home Assistant...")
    if notifier.test_connection():
        print("   [OK] Connection successful!")
    else:
        print("   [X] Connection failed - check URL and token")
        return False

    print("\n2. Testing Alexa notification...")
    print("   Sending test message to your Echo...")

    # Create a test failed item
    test_items = [{"name": "Test Item"}]

    success = notifier.notify_failed_items(test_items)

    if success:
        print("   [OK] Notification sent successfully!")
        print("\n[!] Check your Echo - you should hear:")
        print('   "Attention. I could not add Test Item to the Walmart cart"')
        print("\n" + "="*60)
        print("[OK] ALL TESTS PASSED!")
        print("="*60)
        return True
    else:
        print("   [X] Notification failed - check entity ID and HA logs")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
