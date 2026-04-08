#!/bin/bash
# VPrint Printer Agent - Raspberry Pi 3B+ Automated Setup
# This script automates the installation and configuration of VPrint agent on Raspberry Pi OS
# 
# Usage: 
#   chmod +x setup-rpi.sh
#   ./setup-rpi.sh
#
# Target: Raspberry Pi 3B+ running Raspberry Pi OS (32-bit or 64-bit)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VPRINT_HOME="/home/pi/vprint"
VENV_PATH="/home/pi/vprint-env"
SYSTEMD_SERVICE="/etc/systemd/system/vprint-agent.service"
LOG_FILE="/tmp/vprint-setup.log"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run with sudo"
        exit 1
    fi
}

check_os() {
    log_info "Checking operating system..."
    if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
        log_warn "This appears to be not running on Raspberry Pi (checking /proc/cpuinfo)"
        log_warn "Continuing anyway - may work on Debian/Ubuntu ARM systems"
    else
        log_success "Confirmed running on Raspberry Pi"
    fi
}

update_system() {
    log_info "Updating system packages..."
    apt update
    apt full-upgrade -y
    log_success "System updated"
}

install_system_packages() {
    log_info "Installing system packages..."
    
    # Core packages
    log_info "Installing Python and build tools..."
    apt install -y \
        python3 python3-pip python3-dev python3-venv \
        build-essential libssl-dev libffi-dev
    
    # Printing system
    log_info "Installing CUPS (printing system)..."
    apt install -y \
        cups cups-filters ghostscript
    
    # Canon/GutePrint drivers
    log_info "Installing GutePrint (Canon printer drivers)..."
    apt install -y \
        gutenprint-cups printer-driver-gutenprint
    
    # Document conversion
    log_info "Installing Pandoc (document conversion)..."
    apt install -y pandoc
    
    log_success "System packages installed"
}

setup_cups() {
    log_info "Configuring CUPS..."
    
    # Add pi user to lpadmin group
    usermod -a -G lpadmin,lp pi
    log_success "Added pi to lpadmin and lp groups"
    
    # Start CUPS service
    systemctl start cups
    systemctl enable cups
    log_success "CUPS service started and enabled"
    
    # Wait for CUPS to be ready
    sleep 3
}

setup_python_environment() {
    log_info "Setting up Python virtual environment..."
    
    # Create vprint home directory
    mkdir -p "$VPRINT_HOME"
    chown pi:pi "$VPRINT_HOME"
    
    # Create virtual environment
    python3 -m venv "$VENV_PATH"
    chown -R pi:pi "$VENV_PATH"
    
    log_success "Python virtual environment created at $VENV_PATH"
}

install_python_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Activate venv and install
    sudo -u pi bash << EOF
        source "$VENV_PATH/bin/activate"
        pip install --upgrade pip setuptools wheel
        pip install requests python-dotenv supabase Pillow
EOF
    
    log_success "Python dependencies installed"
}

setup_agent_files() {
    log_info "Setting up VPrint agent files..."
    
    # Check if agent files exist in current directory
    if [ -f "./agent-rpi.py" ]; then
        cp ./agent-rpi.py "$VPRINT_HOME/agent.py"
        log_success "Copied agent-rpi.py to $VPRINT_HOME/agent.py"
    else
        log_warn "agent-rpi.py not found in current directory"
        log_info "Creating placeholder agent..."
        # In production, you'd download from repo
    fi
    
    # Check if .env exists
    if [ ! -f "$VPRINT_HOME/.env" ]; then
        cat > "$VPRINT_HOME/.env" << 'ENVEOF'
# VPrint Agent Configuration
# Update these values with your Supabase credentials

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE=your_service_role_key_here
PRINTER_ID=your-printer-uuid-here
PRINTER_NAME=canon-printer-1

# Optional: Agent behavior
POLL_INTERVAL=3
HEARTBEAT_INTERVAL=5
ENVEOF
        chown pi:pi "$VPRINT_HOME/.env"
        chmod 600 "$VPRINT_HOME/.env"
        log_success "Created .env file - EDIT THIS WITH YOUR CREDENTIALS"
    else
        log_warn ".env already exists, skipping..."
    fi
    
    # Fix permissions
    chown -R pi:pi "$VPRINT_HOME"
    chmod +x "$VPRINT_HOME/agent.py" 2>/dev/null || true
}

setup_systemd_service() {
    log_info "Setting up systemd service..."
    
    cat > "$SYSTEMD_SERVICE" << 'SERVICEEOF'
[Unit]
Description=VPrint Printer Agent
After=network-online.target cups.service
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/vprint
Environment="PATH=/home/pi/vprint-env/bin"
ExecStart=/home/pi/vprint-env/bin/python3 /home/pi/vprint/agent.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF
    
    chmod 644 "$SYSTEMD_SERVICE"
    systemctl daemon-reload
    systemctl enable vprint-agent
    
    log_success "Systemd service installed"
}

verify_installations() {
    log_info "Verifying installations..."
    
    # Check Python
    if python3 --version > /dev/null 2>&1; then
        log_success "Python 3: $(python3 --version)"
    else
        log_error "Python 3 not found"
        return 1
    fi
    
    # Check Pandoc
    if pandoc --version > /dev/null 2>&1; then
        log_success "Pandoc: $(pandoc --version | head -1)"
    else
        log_error "Pandoc not found"
        return 1
    fi
    
    # Check CUPS
    if systemctl is-active --quiet cups; then
        log_success "CUPS: Running"
    else
        log_error "CUPS: Not running"
        return 1
    fi
    
    # Check printer detection
    log_info "Connected printers:"
    lpstat -p -d || log_warn "No printers configured yet"
    
    log_success "Verification complete"
}

print_next_steps() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}VPrint Raspberry Pi Setup Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}IMPORTANT - Next Steps:${NC}"
    echo ""
    echo "1. Configure Supabase credentials:"
    echo "   sudo nano /home/pi/vprint/.env"
    echo ""
    echo "2. Add your printer via CUPS web interface:"
    echo "   http://raspberrypi.local:631"
    echo "   Or use command line: sudo lpadmin -p canon-printer-1 ..."
    echo ""
    echo "3. Test agent manually:"
    echo "   sudo -u pi bash -c 'source /home/pi/vprint-env/bin/activate && python3 /home/pi/vprint/agent.py'"
    echo ""
    echo "4. Enable and start service:"
    echo "   sudo systemctl start vprint-agent"
    echo "   sudo systemctl status vprint-agent"
    echo ""
    echo "5. View live logs:"
    echo "   sudo journalctl -u vprint-agent -f"
    echo ""
    echo -e "${YELLOW}Documentation:${NC}"
    echo "   Setup log: $LOG_FILE"
    echo "   README: /home/pi/vprint/README.md"
    echo ""
    echo -e "${GREEN}For detailed setup instructions, see README-RPI.md${NC}"
    echo ""
}

main() {
    log_info "═══════════════════════════════════════════════════════════"
    log_info "VPrint Printer Agent - Raspberry Pi 3B+ Setup"
    log_info "═══════════════════════════════════════════════════════════"
    log_info ""
    log_info "This script will:"
    log_info "  • Update system packages"
    log_info "  • Install CUPS (printing system)"
    log_info "  • Install GutePrint drivers (Canon support)"
    log_info "  • Install Python and dependencies"
    log_info "  • Configure VPrint agent"
    log_info "  • Setup systemd service (auto-start)"
    log_info ""
    log_info "Press ENTER to continue or CTRL+C to cancel..."
    read -r
    log_info ""
    
    check_root
    check_os
    update_system
    install_system_packages
    setup_cups
    setup_python_environment
    install_python_dependencies
    setup_agent_files
    setup_systemd_service
    verify_installations
    print_next_steps
}

# Run main
main
