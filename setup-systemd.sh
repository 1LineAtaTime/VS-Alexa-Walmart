#!/bin/bash
# Setup script for Amazon-Walmart Automation systemd service

set -e  # Exit on error

echo "======================================================================="
echo "Amazon to Walmart Automation - Systemd Service Setup"
echo "======================================================================="
echo ""

# Get current user and directory
CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)

echo "Current user: $CURRENT_USER"
echo "Current directory: $CURRENT_DIR"
echo ""

# Check if service file exists
if [ ! -f "amazon-walmart-automation.service" ]; then
    echo "ERROR: amazon-walmart-automation.service not found in current directory"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "WARNING: Virtual environment not found at ./venv"
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Installing dependencies..."
    ./venv/bin/pip install -r requirements.txt
    ./venv/bin/playwright install chromium
fi

# Create temporary service file with user-specific paths
echo "Creating systemd service file..."
TEMP_SERVICE=$(mktemp)
sed -e "s|USER|$CURRENT_USER|g" \
    -e "s|/home/USER/VS-Alexa-Walmart|$CURRENT_DIR|g" \
    amazon-walmart-automation.service > "$TEMP_SERVICE"

# Copy to systemd directory
echo "Installing service (requires sudo)..."
sudo cp "$TEMP_SERVICE" /etc/systemd/system/amazon-walmart-automation.service
rm "$TEMP_SERVICE"

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
