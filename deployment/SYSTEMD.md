# Systemd Service Setup for Ubuntu LXC Container

This guide explains how to set up the Amazon-Walmart automation to run continuously as a systemd service on your Ubuntu LXC container.

## Important Notes

⚠️ **Default Configuration:**
- The service is configured to run as **root user**
- Project path is hardcoded to: `/home/VS-Alexa-Walmart`
- This prevents permission issues with git pull on service restarts
- If your project is at a different location, you'll need to manually edit the service file

## Why Systemd Instead of Cron?

Since the automation now runs continuously (checking every 5 seconds), you should use **systemd** instead of cron:

- ✅ Starts automatically on boot
- ✅ Restarts automatically if the program crashes
- ✅ Proper logging with `journalctl`
- ✅ Easy to start/stop/restart
- ✅ Better resource management
- ✅ Auto git pull on every restart to stay updated

## Prerequisites

- **xvfb** must be installed (provides virtual display for non-headless Chrome):
  ```bash
  sudo apt install -y xvfb
  ```
- **Google Chrome** (not Chromium) must be installed for PerimeterX bypass

## Quick Setup (Recommended)

1. **Ensure the project is located at `/home/VS-Alexa-Walmart`:**
   ```bash
   # If not already there, clone or move the project:
   cd /home
   git clone <your-repo-url> VS-Alexa-Walmart
   # OR move existing project:
   # mv ~/VS-Alexa-Walmart /home/VS-Alexa-Walmart
   ```

2. **Navigate to the project directory:**
   ```bash
   cd /home/VS-Alexa-Walmart
   ```

3. **Make the setup script executable:**
   ```bash
   chmod +x deployment/setup-systemd.sh
   ```

4. **Run the setup script:**
   ```bash
   ./deployment/setup-systemd.sh
   ```

5. **First-time setup — establish Walmart session (see below)**

6. **Start the service:**
   ```bash
   sudo systemctl start amazon-walmart-automation
   ```

7. **Check status:**
   ```bash
   sudo systemctl status amazon-walmart-automation
   ```

That's it! The service is now running and will start automatically on boot.

## First-Time Walmart Login

The automation uses a **persistent Chrome browser profile** to maintain login sessions and bypass bot detection (PerimeterX). On first run, Walmart will require 2FA which needs interactive input.

### Option A: Run once interactively (recommended)

Stop the service and run the automation once interactively so you can enter the 2FA code:

```bash
# Stop the service if running
sudo systemctl stop amazon-walmart-automation

# Run once interactively with xvfb
cd /home/VS-Alexa-Walmart
xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24' \
  .venv/bin/python src/main.py --once
```

When prompted, enter the 6-digit 2FA code from your email. After successful login, the persistent profile will remember the session and 2FA won't be needed again.

Then restart the service:
```bash
sudo systemctl start amazon-walmart-automation
```

### Option B: Copy profile from Windows

If you've already logged into Walmart on your Windows machine using `manual_login.py`, copy the persistent profile to the LXC:

```bash
# From your Windows machine (Git Bash or PowerShell with SSH)
scp -r credentials/.playwright_profile root@<LXC-IP>:/home/VS-Alexa-Walmart/credentials/.playwright_profile
```

### Option C: Manual login script

Run the manual login helper (opens a browser for you to log in manually):

```bash
cd /home/VS-Alexa-Walmart
xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24' \
  .venv/bin/python manual_login.py
```

Note: On a headless LXC this won't show a visible browser. Use Option A or B instead.

## Manual Setup (Alternative)

If you prefer to set up manually:

1. **Ensure project is at `/home/VS-Alexa-Walmart`** (service is configured for this path)

2. **Copy service file to systemd directory:**
   ```bash
   sudo cp deployment/amazon-walmart-automation.service /etc/systemd/system/
   ```

   Note: The service file is pre-configured for root user at `/home/VS-Alexa-Walmart`.
   If you need different settings, edit the file before copying.

3. **Set up virtual environment:**
   ```bash
   cd /home/VS-Alexa-Walmart
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/playwright install chromium
   ```

4. **Reload systemd:**
   ```bash
   sudo systemctl daemon-reload
   ```

5. **Enable the service:**
   ```bash
   sudo systemctl enable amazon-walmart-automation
   ```

6. **Start the service:**
   ```bash
   sudo systemctl start amazon-walmart-automation
   ```

## Service Management Commands

### Start the service
```bash
sudo systemctl start amazon-walmart-automation
```

### Stop the service
```bash
sudo systemctl stop amazon-walmart-automation
```

### Restart the service
```bash
sudo systemctl restart amazon-walmart-automation
```

### Check status
```bash
sudo systemctl status amazon-walmart-automation
```

### Enable auto-start on boot
```bash
sudo systemctl enable amazon-walmart-automation
```

### Disable auto-start on boot
```bash
sudo systemctl disable amazon-walmart-automation
```

## Viewing Logs

### View live logs (follow mode)
```bash
sudo journalctl -u amazon-walmart-automation -f
```

### View last 100 lines
```bash
sudo journalctl -u amazon-walmart-automation -n 100
```

### View logs since today
```bash
sudo journalctl -u amazon-walmart-automation --since today
```

### View logs for a specific time range
```bash
sudo journalctl -u amazon-walmart-automation --since "2025-11-13 10:00:00" --until "2025-11-13 12:00:00"
```

## Configuration

### Change Schedule Interval

Edit `src/config.py` or set environment variables:

```bash
sudo systemctl edit amazon-walmart-automation
```

Add environment variables:
```ini
[Service]
Environment="APP_SCHEDULE_INTERVAL_MIN_MINUTES=3"
Environment="APP_SCHEDULE_INTERVAL_MAX_MINUTES=5"
```

Then restart:
```bash
sudo systemctl restart amazon-walmart-automation
```

### Run Once Interactively (for testing/debugging)

Stop the service and run a single pass:
```bash
sudo systemctl stop amazon-walmart-automation
cd /home/VS-Alexa-Walmart
xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24' \
  .venv/bin/python src/main.py --once
```

The `--once` flag runs a single check cycle and exits instead of continuous monitoring.

## Troubleshooting

### Service won't start

1. Check the status for errors:
   ```bash
   sudo systemctl status amazon-walmart-automation
   ```

2. View detailed logs:
   ```bash
   sudo journalctl -u amazon-walmart-automation -n 50
   ```

3. Verify Python virtual environment exists:
   ```bash
   ls -la /home/VS-Alexa-Walmart/.venv
   ```

4. Test running manually:
   ```bash
   cd /home/VS-Alexa-Walmart
   ./.venv/bin/python src/main.py
   ```

### Credentials issues

If you see authentication errors, ensure credentials are configured:

```bash
ls -la /home/VS-Alexa-Walmart/credentials/credentials.py
```

If missing, copy from example:
```bash
cd /home/VS-Alexa-Walmart
cp credentials.py.example credentials/credentials.py
nano credentials/credentials.py  # Edit with your credentials
```

### Permission issues

The service is configured to run as root by default:

```bash
sudo systemctl cat amazon-walmart-automation | grep User=
```

Should show `User=root`

If you need to run as a different user, edit the service file and adjust paths accordingly.

### High memory usage

If the browser uses too much memory, you can restart the service daily:

Create a systemd timer:
```bash
sudo nano /etc/systemd/system/amazon-walmart-automation-restart.timer
```

```ini
[Unit]
Description=Daily restart of Amazon-Walmart automation

[Timer]
OnCalendar=daily
OnCalendar=04:00
Persistent=true

[Install]
WantedBy=timers.target
```

Create the service:
```bash
sudo nano /etc/systemd/system/amazon-walmart-automation-restart.service
```

```ini
[Unit]
Description=Restart Amazon-Walmart automation

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart amazon-walmart-automation.service
```

Enable the timer:
```bash
sudo systemctl enable amazon-walmart-automation-restart.timer
sudo systemctl start amazon-walmart-automation-restart.timer
```

## Monitoring

### Check if service is running
```bash
systemctl is-active amazon-walmart-automation
```

### Check if service is enabled
```bash
systemctl is-enabled amazon-walmart-automation
```

### View service uptime
```bash
systemctl show amazon-walmart-automation --property=ActiveEnterTimestamp
```

## Updating the Code

When you pull new changes from git:

1. **Stop the service:**
   ```bash
   sudo systemctl stop amazon-walmart-automation
   ```

2. **Pull updates:**
   ```bash
   git pull
   ```

3. **Update dependencies (if needed):**
   ```bash
   ./.venv/bin/pip install -r requirements.txt
   ```

4. **Restart the service:**
   ```bash
   sudo systemctl start amazon-walmart-automation
   ```

## Uninstalling

To remove the systemd service:

```bash
# Stop and disable
sudo systemctl stop amazon-walmart-automation
sudo systemctl disable amazon-walmart-automation

# Remove service file
sudo rm /etc/systemd/system/amazon-walmart-automation.service

# Reload systemd
sudo systemctl daemon-reload
```

## LXC Container Specific Notes

### Auto-start on LXC Host Boot

Ensure your LXC container auto-starts:

On the **LXC host** (not in the container):
```bash
pct set <CTID> --onboot 1
```

Replace `<CTID>` with your container ID.

### Resource Limits

If you need to limit resources, edit on the **LXC host**:

```bash
pct set <CTID> --memory 2048 --cores 2
```

This limits the container to 2GB RAM and 2 CPU cores.

## Additional Tips

- **Log Rotation**: Systemd automatically rotates logs, but you can configure limits:
  ```bash
  sudo journalctl --vacuum-size=100M
  sudo journalctl --vacuum-time=30d
  ```

- **Monitor Resource Usage**:
  ```bash
  systemctl status amazon-walmart-automation | grep Memory
  ```

- **Email Notifications**: Consider setting up systemd failure notifications with `OnFailure=` directive and a notification service.
