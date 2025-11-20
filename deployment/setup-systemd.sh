#!/bin/bash
# Setup script for Amazon-Walmart Automation systemd service

set -e  # Exit on error

echo "======================================================================="
echo "Amazon to Walmart Automation - Systemd Service Setup"
echo "======================================================================="
echo ""

# Get script directory (deployment folder) and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Get current user
CURRENT_USER=$(whoami)

echo "Current user: $CURRENT_USER"
echo "Project directory: $PROJECT_ROOT"
echo ""
echo "NOTE: Service is configured to run as root user at /home/VS-Alexa-Walmart"
echo "      If your project is at a different location, you may need to adjust the service file manually."
echo ""

# Check if service file exists
if [ ! -f "$SCRIPT_DIR/amazon-walmart-automation.service" ]; then
    echo "ERROR: amazon-walmart-automation.service not found in $SCRIPT_DIR"
    echo "Please ensure the file is in the deployment directory"
    exit 1
fi

# Check if virtual environment exists at the expected location
if [ ! -d "/home/VS-Alexa-Walmart/.venv" ]; then
    echo "WARNING: Virtual environment not found at /home/VS-Alexa-Walmart/.venv"
    echo "Creating virtual environment..."
    python3 -m venv /home/VS-Alexa-Walmart/.venv
    echo "Installing dependencies..."
    /home/VS-Alexa-Walmart/.venv/bin/pip install -r /home/VS-Alexa-Walmart/requirements.txt
    /home/VS-Alexa-Walmart/.venv/bin/playwright install chromium
fi

# Copy service file directly (no replacement needed - paths are hardcoded)
echo "Installing service (requires sudo)..."
sudo cp "$SCRIPT_DIR/amazon-walmart-automation.service" /etc/systemd/system/amazon-walmart-automation.service

# Set permissions
sudo chmod 644 /etc/systemd/system/amazon-walmart-automation.service

# Reload systemd
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable service to start on boot
echo "Enabling service to start on boot..."
sudo systemctl enable amazon-walmart-automation.service

echo ""
echo "======================================================================="
echo "Installation complete!"
echo "======================================================================="
echo ""
echo "Service commands:"
echo "  Start:   sudo systemctl start amazon-walmart-automation"
echo "  Stop:    sudo systemctl stop amazon-walmart-automation"
echo "  Restart: sudo systemctl restart amazon-walmart-automation"
echo "  Status:  sudo systemctl status amazon-walmart-automation"
echo "  Logs:    sudo journalctl -u amazon-walmart-automation -f"
echo ""
echo "The service is enabled and will start automatically on boot."
echo ""
echo "To start the service now, run:"
echo "  sudo systemctl start amazon-walmart-automation"
echo ""
