# Amazon Alexa to Walmart Shopping List Automation

Automates the process of transferring shopping list items from Amazon Alexa to your Walmart cart using browser automation.

## Overview

This tool automatically:
1. Authenticates with Amazon and Walmart
2. Continuously monitors your Amazon Alexa shopping list (checks every 5 seconds)
3. When items are detected, scrapes and saves them to a local text file
4. Clears items from the Amazon list
5. Searches for matching products on Walmart and adds them to your cart
6. Uses "My Items" (previously purchased) as a fallback for better matching
7. If My Items fails, tries adding the first 10 items from search results sequentially
8. Sends Alexa voice notifications via Home Assistant for any items that fail to add

## Quick Start

### Prerequisites

- Python 3.9 or higher
- Google Chrome installed (recommended) or Chromium
- Amazon account with Alexa shopping list
- Walmart account
- For LXC: Proxmox host access for container configuration

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd VS-Alexa-Walmart
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium  # Fallback if Chrome not installed
```

4. Configure credentials:
```bash
cp credentials/credentials.py.example credentials/credentials.py
# Edit credentials/credentials.py with your actual credentials
```

### Usage

**Run once (for testing):**
```bash
python src/main.py --once
```

**Run with continuous monitoring (checks every 5 seconds, refreshes every 10-15 minutes):**
```bash
python src/main.py
```

**Run with visible browser (for debugging):**
```bash
APP_BROWSER_HEADLESS=false python src/main.py --once
```

The continuous monitoring mode will:
- Check for new items every 5 seconds
- Refresh the Amazon page every 10-15 minutes (random interval) if no new items
- Process items immediately when detected
- Keep browsers open between checks to save resources

## Running in Proxmox LXC Container

If you're running this in a Proxmox LXC container, you need to configure the container to allow Chrome/Chromium to access the network.

### Required LXC Configuration

**On the Proxmox host**, edit your container config file:

```bash
# Find your container ID
pct list

# Edit the config (replace <CTID> with your container ID)
nano /etc/pve/lxc/<CTID>.conf
```

**Add these lines to the end of the file:**

```
lxc.apparmor.profile: unconfined
lxc.cap.drop:
lxc.mount.auto: proc:rw sys:rw
```

**Enable nesting:**

```bash
pct set <CTID> -features nesting=1
```

**Restart the container:**

```bash
pct restart <CTID>
```

### Install Google Chrome (Recommended)

Chrome works better than Chromium for avoiding bot detection:

```bash
# Inside the LXC container
cd /tmp
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
sudo apt --fix-broken install  # If needed
rm google-chrome-stable_current_amd64.deb
```

### Systemd Service Setup

For continuous operation, set up a systemd service:

⚠️ **Important**: The systemd service is configured to:
- Run as **root user** (prevents permission issues with git pull)
- Expect project location at `/home/VS-Alexa-Walmart`
- Auto git pull on every service restart to stay updated

```bash
# Ensure project is at the correct location
# If not already there, move or clone to /home/VS-Alexa-Walmart
cd /home
git clone <repository-url> VS-Alexa-Walmart

# Navigate to project
cd /home/VS-Alexa-Walmart

# Make setup script executable
chmod +x deployment/setup-systemd.sh

# Run setup (installs and enables service)
./deployment/setup-systemd.sh

# Start the service
sudo systemctl start amazon-walmart-automation

# View logs
sudo journalctl -u amazon-walmart-automation -f
```

See [deployment/SYSTEMD.md](deployment/SYSTEMD.md) for detailed service management.

### Troubleshooting LXC

**If Chrome shows `ERR_INTERNET_DISCONNECTED`:**
- Verify the LXC config has the 3 lines above
- Ensure `features: nesting=1` is enabled
- Restart the container after making changes

**Test Chrome network access:**
```bash
google-chrome --headless --disable-gpu --dump-dom https://www.google.com
```

If this works, the automation will work too.

## How It Works

The automation is organized into 4 modules:

### Module 0: Authentication
- Authenticates with Amazon using OTP/TOTP
- Authenticates with Walmart using email 2FA
- Persists sessions via cookies for faster subsequent runs

### Module 1: Amazon Scraping
- Navigates to Amazon Alexa shopping list
- Scrapes all items with quantities
- Handles dynamic loading and multiple page formats

### Module 2: Save & Clear
- Saves scraped items to timestamped `.txt` file
- Clears all items from Amazon Alexa shopping list
- Deletes `.txt` file after successful cart addition

### Module 3: Walmart Search & Add
- Searches Walmart catalog for each item
- Selects top product based on purchase frequency
- Attempts to add from search results
- **Fallback 1**: If search fails, searches "My Items" (previously purchased items) using fuzzy matching
- Batch processes all failed items in a single My Items scan for efficiency
- **Fallback 2**: If My Items fails, tries adding the first 10 items from search results sequentially
- **Fallback 3**: Sends Alexa voice notification via Home Assistant for any items that still fail

## Key Features

### Continuous Monitoring
- Checks Alexa shopping list every 5 seconds for new items
- Automatically refreshes page every 10-15 minutes (random interval) to prevent session timeouts
- Processes items immediately when detected
- No manual intervention needed

### Smart Matching
- Uses product name from search results for better fuzzy matching
- Prioritizes "frequently bought" items
- Higher match score threshold (60) for My Items to avoid false positives

### Triple Fallback System
1. **Primary**: Add top product from Walmart search results
2. **Fallback 1**: Batch search through "My Items" (previously purchased) with fuzzy matching
3. **Fallback 2**: Try adding first 10 items from search results sequentially
4. **Notification**: Alexa voice alert via Home Assistant for any failures

### Batch My Items Fallback
- Processes multiple failed items efficiently
- Single scan through My Items for all failed items
- Navigates to specific My Items page for each matched product

### Home Assistant Integration
- Sends Alexa voice notifications for failed items
- Example: "Attention. I could not add milk to the Walmart cart"
- Requires Alexa Media Player integration in Home Assistant

### Persistent Browser Sessions
- Keeps browser open between scheduled runs
- Reduces authentication overhead
- Saves resources by avoiding repeated browser launches

### Error Handling
- Screenshots saved on errors
- Failed items tracked separately
- Partial success supported (updates `.txt` file)

## Project Structure

```
VS-Alexa-Walmart/
├── src/
│   ├── main.py              # Main orchestration (4 modules)
│   ├── config.py            # Configuration & settings
│   ├── auth/                # Module 0: Authentication
│   │   ├── amazon_auth.py
│   │   ├── walmart_auth.py
│   │   └── session_manager.py
│   ├── amazon/              # Module 1 & 2: Amazon operations
│   │   ├── list_scraper.py
│   │   └── list_clearer.py
│   ├── walmart/             # Module 3: Walmart operations
│   │   ├── product_search.py
│   │   └── cart_manager.py
│   ├── search/              # Fuzzy matching for products
│   │   └── matcher.py
│   └── utils/
│       └── logger.py
├── deployment/              # Systemd service files for Linux
│   ├── setup-systemd.sh
│   ├── amazon-walmart-automation.service
│   └── SYSTEMD.md
├── credentials/             # Your credentials (gitignored)
├── logs/                    # Log files & screenshots (auto-generated)
├── requirements.txt
├── README.md
└── CLAUDE.md               # Development notes for Claude Code
```

## Configuration

Edit `credentials/credentials.py`:

```python
# Amazon credentials
AMAZON_EMAIL = "your-email@example.com"
AMAZON_PASSWORD = "your-password"
AMAZON_OTP_SECRET = "your-otp-secret"  # For 2FA

# Walmart credentials
WALMART_EMAIL = "your-email@example.com"
WALMART_PASSWORD = "your-password"

# Home Assistant (optional - for Alexa notifications)
HOME_ASSISTANT_URL = "http://homeassistant.local:8123"
HOME_ASSISTANT_TOKEN = "your-long-lived-access-token"
HOME_ASSISTANT_ALEXA_ENTITY = "media_player.echo_show"
```

### Home Assistant Setup (Optional)

To enable Alexa voice notifications for failed items:

1. **Install Alexa Media Player integration in Home Assistant:**
   - Go to Settings → Devices & Services → Add Integration
   - Search for "Alexa Media Player" and install
   - Follow the setup wizard to connect your Amazon account

2. **Create a Long-Lived Access Token:**
   - In Home Assistant, click your profile (bottom left), then Security tab
   - Scroll down to "Long-Lived Access Tokens"
   - Click "Create Token"
   - Give it a name like "Amazon Walmart Automation"
   - Copy the token and paste it in `credentials.py`

3. **Find your Alexa device entity ID:**
   - Go to Settings → Devices & Services → Entities
   - Search for your Echo device (e.g., "Echo Show")
   - Copy the entity ID (e.g., `media_player.echo_show`)
   - Paste it in `credentials.py`

4. **Test the connection:**
   ```python
   from src.notifications import HomeAssistantNotifier
   notifier = HomeAssistantNotifier()
   notifier.test_connection()
   ```

If configured correctly, when items fail to add to the Walmart cart, your Echo will announce: "Attention. I could not add [item names] to the Walmart cart"

### Environment Variables

All settings can be overridden with `APP_` prefix:

```bash
APP_BROWSER_HEADLESS=false              # Show browser (default: true)
APP_MIN_MATCH_SCORE=70                  # Fuzzy match threshold (default: 70)
APP_MONITOR_INTERVAL_SECONDS=5          # Check interval (default: 5)
APP_SCHEDULE_INTERVAL_MIN_MINUTES=10    # Min refresh interval (default: 10)
APP_SCHEDULE_INTERVAL_MAX_MINUTES=15    # Max refresh interval (default: 15)
APP_SEARCH_FALLBACK_MAX_ITEMS=10        # Max items to try from search (default: 10)
```

## Troubleshooting

### Authentication Issues

**Amazon authentication fails - Button click not working:**

If you see logs like:
- "Still on sign-in page after clicking Sign-In"
- "URL did not change after clicking Sign-In"
- "OTP not required" when it should be

This indicates Amazon's bot detection is blocking the form submission. The code now uses multiple submission methods including JavaScript form submission to bypass this.

**Solution:**
```bash
# 1. Delete old cookies
rm credentials/*_cookies.json

# 2. Verify the fix is in place
# Check that amazon_auth.py uses form.submit() method (already fixed)

# 3. Test authentication
python src/main.py --once

# 4. Check logs for these success indicators:
# - "Method 3: Submitting form directly with JavaScript..."
# - "OTP page detected by URL"
# - "OTP verification required"
# - "Amazon authentication successful"
```

**If authentication still fails:**
- Amazon may be blocking your IP address - try from a different network
- CAPTCHA may be required - the code will detect this and notify you
- Check `logs/` directory for error screenshots
- Verify OTP secret is correctly configured in `credentials/credentials.py`

**OTP Issues:**
- OTP codes are time-sensitive - ensure system clock is accurate
- The code adds a 3-second delay before generating OTP for better sync
- Check logs for "Generated OTP code" - should be 6 digits

### General Issues

**Items not matching:**
- Adjust `APP_MIN_MATCH_SCORE` (lower = more lenient, higher = stricter)
- Check logs for match scores
- Products not previously purchased won't be in "My Items"

**Selectors broken (website changed):**
- Check `logs/` directory for screenshots
- Update selectors in respective scraper files
- Always provide multiple fallback selector options

## Logs

- **Console**: INFO level, colored output
- **Files**: `logs/automation_YYYY-MM-DD.log` (DEBUG level)
- **Screenshots**: `logs/*_error_*.png` (on failures)
- **Rotation**: Daily rotation, 30-day retention

## License

MIT License - see LICENSE file

## Security Notes

- All credentials stored locally only
- Cookies are browser-encrypted at rest
- No external data transmission except to Amazon/Walmart
- Never commit `credentials/credentials.py` or `*_cookies.json`
