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

# Check if service file exists
if [ ! -f "$SCRIPT_DIR/amazon-walmart-automation.service" ]; then
    echo "ERROR: amazon-walmart-automation.service not found in $SCRIPT_DIR"
    echo "Please ensure the file is in the deployment directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "WARNING: Virtual environment not found at $PROJECT_ROOT/venv"
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_ROOT/venv"
    echo "Installing dependencies..."
    "$PROJECT_ROOT/venv/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"
    "$PROJECT_ROOT/venv/bin/playwright" install chromium
fi

# Create temporary service file with user-specific paths
echo "Creating systemd service file..."
TEMP_SERVICE=$(mktemp)
sed -e "s|USER|$CURRENT_USER|g" \
    -e "s|/home/USER/VS-Alexa-Walmart|$PROJECT_ROOT|g" \
    "$SCRIPT_DIR/amazon-walmart-automation.service" > "$TEMP_SERVICE"

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
