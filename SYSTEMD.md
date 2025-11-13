# Systemd Service Setup for Ubuntu LXC Container

This guide explains how to set up the Amazon-Walmart automation to run continuously as a systemd service on your Ubuntu LXC container.

## Why Systemd Instead of Cron?

Since the automation now runs continuously (checking every 3-5 minutes), you should use **systemd** instead of cron:

- ✅ Starts automatically on boot
- ✅ Restarts automatically if the program crashes
- ✅ Proper logging with `journalctl`
- ✅ Easy to start/stop/restart
- ✅ Better resource management

## Quick Setup (Recommended)

1. **Navigate to the project directory:**
   ```bash
   cd ~/VS-Alexa-Walmart
   ```

2. **Make the setup script executable:**
   ```bash
   chmod +x setup-systemd.sh
   ```

3. **Run the setup script:**
   ```bash
   ./setup-systemd.sh
   ```

4. **Start the service:**
   ```bash
   sudo systemctl start amazon-walmart-automation
   ```

5. **Check status:**
   ```bash
   sudo systemctl status amazon-walmart-automation
   ```

That's it! The service is now running and will start automatically on boot.

## Manual Setup (Alternative)

If you prefer to set up manually:

1. **Edit the service file:**
   ```bash
   nano amazon-walmart-automation.service
   ```

   Replace `USER` with your actual username and adjust paths if needed.

2. **Copy to systemd directory:**
   ```bash
   sudo cp amazon-walmart-automation.service /etc/systemd/system/
   ```

3. **Reload systemd:**
   ```bash
   sudo systemctl daemon-reload
   ```

4. **Enable the service:**
   ```bash
   sudo systemctl enable amazon-walmart-automation
   ```

5. **Start the service:**
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

### Run in Headed Mode (for debugging)

```bash
sudo systemctl edit amazon-walmart-automation
```

Add:
```ini
[Service]
Environment="APP_BROWSER_HEADLESS=false"
```

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
   ls -la ~/VS-Alexa-Walmart/venv
   ```

4. Test running manually:
   ```bash
   cd ~/VS-Alexa-Walmart
   ./venv/bin/python src/main.py
   ```

### Credentials issues

If you see authentication errors, ensure credentials are configured:

```bash
ls -la ~/VS-Alexa-Walmart/credentials/credentials.py
```

If missing, copy from example:
```bash
cp credentials.py.example credentials/credentials.py
nano credentials/credentials.py  # Edit with your credentials
```

### Permission issues

Ensure the service runs as your user (not root):

```bash
sudo systemctl cat amazon-walmart-automation | grep User=
```

Should show `User=your-username`

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
   ./venv/bin/pip install -r requirements.txt
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
