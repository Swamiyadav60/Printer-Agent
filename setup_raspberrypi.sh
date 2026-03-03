#!/bin/bash

# VPrint Raspberry Pi Zero W - Automated Setup Script
# This script automates the entire setup process on Raspberry Pi

set -e  # Exit on error

echo "=========================================="
echo "VPrint Raspberry Pi Setup Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Step 1: Update System
echo ""
print_status "Step 1: Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Step 2: Install CUPS
echo ""
print_status "Step 2: Installing CUPS (printer service)..."
sudo apt-get install -y cups cups-client libcups2-dev

# Step 3: Add pi user to lpadmin group
echo ""
print_status "Step 3: Configuring printer permissions..."
sudo usermod -a -G lpadmin pi

# Step 4: Start CUPS service
echo ""
print_status "Step 4: Starting CUPS service..."
sudo systemctl start cups
sudo systemctl enable cups

# Step 5: Install Python
echo ""
print_status "Step 5: Installing Python and pip..."
sudo apt-get install -y python3 python3-pip python3-venv

# Step 6: Clone repository
echo ""
print_warning "Step 6: Cloning VPrint repository..."
if [ ! -d ~/print666 ]; then
    read -p "Enter your Git repository URL: " GIT_URL
    git clone $GIT_URL ~/print666
    print_status "Repository cloned to ~/print666"
else
    print_warning "Repository already exists at ~/print666"
fi

cd ~/print666/print/printer-agent

# Step 7: Create Python virtual environment
echo ""
print_status "Step 7: Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Step 8: Install Python dependencies
echo ""
print_status "Step 8: Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

deactivate

# Step 9: Create .env file
echo ""
print_warning "Step 9: Configuring environment variables..."

if [ -f .env ]; then
    print_warning ".env file already exists. Skipping..."
else
    cp .env.example .env
    print_warning "Please edit .env file with your Supabase credentials:"
    print_warning "  nano .env"
    print_warning ""
    print_warning "Required values:"
    print_warning "  - SUPABASE_URL"
    print_warning "  - SUPABASE_SERVICE_ROLE"
    print_warning "  - PRINTER_ID"
fi

# Step 10: Test printer
echo ""
print_status "Step 10: Checking for USB printers..."
echo ""
lpstat -p -d
echo ""

# Step 11: Test agent
echo ""
print_warning "Step 11: Testing VPrint Agent..."
print_warning "Starting agent in test mode. Press Ctrl+C to stop."
print_warning ""

source venv/bin/activate
python3 agent_linux.py &
AGENT_PID=$!
sleep 5
kill $AGENT_PID 2>/dev/null || true
deactivate

# Step 12: Install systemd service
echo ""
print_status "Step 12: Installing systemd service..."

# Create the service file
sudo tee /etc/systemd/system/vprint-agent.service > /dev/null << 'EOF'
[Unit]
Description=VPrint Printer Agent Service
After=network-online.target
Wants=network-online.target
StartLimitBurst=5
StartLimitIntervalSec=60

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/print666/print/printer-agent
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 /home/pi/print666/print/printer-agent/agent_linux.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vprint-agent

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vprint-agent

print_status "Systemd service installed and enabled"

# Step 13: Summary
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
print_status "Next steps:"
echo "  1. Edit .env with your Supabase credentials:"
echo "     nano ~/print666/print/printer-agent/.env"
echo ""
echo "  2. Verify printer is connected:"
echo "     lpstat -p -d"
echo ""
echo "  3. Start the agent service:"
echo "     sudo systemctl start vprint-agent"
echo ""
echo "  4. Check if service is running:"
echo "     sudo systemctl status vprint-agent"
echo ""
echo "  5. View logs in real-time:"
echo "     sudo journalctl -u vprint-agent -f"
echo ""
echo "=========================================="
echo ""
