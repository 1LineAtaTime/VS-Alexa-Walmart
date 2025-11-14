# Amazon Alexa to Walmart Shopping List Automation

Automates the process of transferring shopping list items from Amazon Alexa to your Walmart cart using browser automation.

## Overview

This tool automatically:
1. Authenticates with Amazon and Walmart
2. Scrapes items from your Amazon Alexa shopping list
3. Saves items to a local text file and clears the Amazon list
4. Searches for matching products on Walmart and adds them to your cart
5. Uses "My Items" (previously purchased) as a fallback for better matching

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

**Run on schedule (every 5 minutes):**
```bash
python src/main.py
```

**Run with visible browser (for debugging):**
```bash
APP_BROWSER_HEADLESS=false python src/main.py --once
```

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

```bash
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
- **Fallback**: If search fails, searches "My Items" (previously purchased items) using fuzzy matching
- Batch processes all failed items in a single My Items scan for efficiency

## Key Features

### Smart Matching
- Uses product name from search results for better fuzzy matching
- Prioritizes "frequently bought" items
- Higher match score threshold (60) for My Items to avoid false positives

### Batch My Items Fallback
- Processes multiple failed items efficiently
- Single scan through My Items for all failed items
- Navigates to specific My Items page for each matched product

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
```

### Environment Variables

All settings can be overridden with `APP_` prefix:

```bash
APP_BROWSER_HEADLESS=false    # Show browser (default: true)
APP_MIN_MATCH_SCORE=70        # Fuzzy match threshold (default: 70)
APP_SCHEDULE_INTERVAL_MINUTES=5  # Run every N minutes (default: 5)
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
