# VPrint Raspberry Pi OS 32-bit Lite + Epson Printer Setup

## Specific Guide for 32-bit Lite Version

**Supports:**

- ✓ Epson L3210 (newer, faster, ~38 ppm)
- ✓ Epson L130 (older, slower, ~27 ppm but cheaper)
- ✓ Any USB-connected Epson printer with CUPS support

---

## Key Difference: 32-bit vs 64-bit

Your setup uses **Raspberry Pi OS 32-bit Lite**, which affects:

- Python version support
- Package availability
- Memory usage (lighter footprint - good for Pi Zero W!)
- Installation commands

---

## QUICK START: 32-bit Lite Specific Commands

### Step 1: Connect via SSH

```bash
ssh pi@vprint-rpi.local
# Password: (your password)
```

### Step 2: Update System (32-bit specific)

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y apt-transport-https
```

### Step 3: Install CUPS & Epson Drivers (32-bit compatible)

```bash
# CUPS installation
sudo apt-get install -y cups cups-client libcups2-dev

# Epson printer drivers (32-bit compatible)
sudo apt-get install -y printer-driver-escpr

# Note: printer-driver-escpr2 may not be available for 32-bit
# That's OK - escpr alone works fine for Epson L3210

# Additional printer support
sudo apt-get install -y cups-filters cups-bsd
```

### Step 4: Configure CUPS Permissions

```bash
# Start CUPS
sudo systemctl start cups
sudo systemctl enable cups

# Add pi user to printer groups
sudo usermod -a -G lpadmin pi
sudo usermod -a -G lp pi

# Verify groups
groups pi
# Should show: pi adm dialout cdrom sudo gpio i2c spi lpadmin lp

# Restart CUPS to apply permissions
sudo systemctl restart cups
```

### Step 5: Check Printer Detection

```bash
# Wait 15 seconds for USB detection
sleep 15

# List printers
lpstat -p -d

# You should see something like:
# printer Epson_L3210 is idle. enabled since...
```

### Step 6: Test Manual Print

```bash
# Create test file
echo "Test Print - Raspberry Pi OS 32-bit Lite" > test.txt

# Print to Epson L3210
lp -d Epson_L3210 test.txt

# Check if Epson L3210 printed a page
```

---

## Step 7: Install Python (32-bit specific)

```bash
# Check if Python3 is installed (usually pre-installed)
python3 --version

# Install pip and development tools
sudo apt-get install -y python3-pip python3-dev python3-venv

# Verify pip works
pip3 --version
```

### Check Available Python Version

```bash
# On Raspberry Pi OS 32-bit Lite, you'll typically have:
# - Python 3.9 or 3.11 (depending on release date)

python3 --version
```

---

## Step 8: Clone VPrint Repository

```bash
# Install git (if not already installed)
sudo apt-get install -y git

# Clone repository
git clone https://github.com/YOUR_USERNAME/print666.git

# Navigate to agent folder
cd print666/print/printer-agent

# Verify files exist
ls -la
# Should show: agent_linux.py, .env.example, requirements-linux.txt, etc.
```

---

## Step 9: Install Python Dependencies (32-bit optimized)

```bash
# Navigate to agent folder
cd ~/print666/print/printer-agent

# Create virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip3 install --upgrade pip

# Install dependencies
pip3 install -r requirements-linux.txt

# Expected packages:
# - requests
# - python-dotenv
# - supabase
# - pypdf

# Verify installation
pip3 list | grep -E "requests|supabase|pypdf|python-dotenv"
```

### If Installation Fails

For 32-bit Lite, sometimes packages need building from source:

```bash
# Install build tools if needed
sudo apt-get install -y build-essential python3-dev libssl-dev libffi-dev

# Retry installation
pip3 install -r requirements-linux.txt
```

---

## Step 10: Configure .env File

```bash
# Navigate to agent folder
cd ~/print666/print/printer-agent

# Create .env (copy from example)
cp .env.example .env

# Edit with your values
nano .env
```

**Fill in with YOUR values:**

```env
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
PRINTER_ID=550e8400-e29b-41d4-a716-446655440000
PRINTER_NAME=Epson_L3210
POLL_INTERVAL=3
```

**Save:** Ctrl+X → Y → Enter

### Verify .env Permissions (Important!)

```bash
# Make .env readable only by pi user (security)
chmod 600 .env

# Verify
ls -la .env
# Should show: -rw------- (600 permissions)
```

---

## Step 11: Test VPrint Agent

```bash
# Navigate to agent folder
cd ~/print666/print/printer-agent

# If using virtual environment, activate it first
source venv/bin/activate

# Test the agent (run for 10 seconds, then Ctrl+C)
python3 agent_linux.py

# You should see:
# 2025-03-02 10:15:30 | INFO     | ==========================================
# 2025-03-02 10:15:30 | INFO     | VPrint Agent Started (Linux) | Printer: xxxx
# 2025-03-02 10:15:30 | INFO     | ==========================================
# 2025-03-02 10:15:31 | INFO     | Initialized API Manager with: https://smartprinter.in/api/jobs
```

**If errors occur:** Check the Troubleshooting section at the bottom

---

## Step 12: Setup Systemd Service (Auto-start)

### Option A: Using vprint-agent.service

```bash
# Copy service file to system
sudo cp ~/print666/print/printer-agent/vprint-agent.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable vprint-agent

# Start service now
sudo systemctl start vprint-agent

# Check status
sudo systemctl status vprint-agent

# You should see "active (running)"
```

### Option B: Manual Service File (if file doesn't exist)

```bash
# Create service file
sudo nano /etc/systemd/system/vprint-agent.service
```

**Paste this content:**

```ini
[Unit]
Description=VPrint Printer Agent
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
```

**Save:** Ctrl+X → Y → Enter

**Then enable:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent
sudo systemctl status vprint-agent
```

---

## Step 13: Verify Everything Works

### Check Service Status

```bash
sudo systemctl status vprint-agent

# Should show:
# ● vprint-agent.service - VPrint Printer Agent
#    Loaded: loaded
#    Active: active (running)
```

### Watch Live Logs

```bash
# Real-time logs
sudo journalctl -u vprint-agent -f

# Should show agent polling for jobs
# Press Ctrl+C to exit
```

### Test Printer

```bash
# Check printer is detected
lpstat -p -d

# Manual test print
echo "Test from 32-bit Lite" | lp -d Epson_L3210
```

---

## Step 14: End-to-End Test

### 1. Upload Test Job via Frontend

1. Open your VPrint frontend (Vercel URL or localhost)
2. Click **"Start Printing"**
3. Upload a PDF file
4. Set options (1 copy, all pages)
5. Make payment (test card: 4111 1111 1111 1111)

### 2. Monitor Agent Logs

```bash
# On Raspberry Pi, watch logs:
sudo journalctl -u vprint-agent -f

# You should see:
# --- Starting Job: xxxx ---
# Downloading file from Supabase...
# Executing print command: lp -d Epson_L3210 /tmp/vprint_xxx.pdf
# --- Job xxxx Completed Successfully ---
```

### 3. Check Printer

Go to your **Epson L3210** printer → Your PDF should print within 10 seconds!

---

## 32-bit Lite Specific Considerations

### Memory Usage

- 32-bit OS uses less RAM (good for Pi Zero W!)
- Agent typically uses 50-100 MB
- CUPS uses ~20 MB
- Python runtime: ~30 MB

**Total typical memory: ~100-150 MB** ✓ No issues

### Storage

- 32-bit OS: ~1-2 GB after installation
- Your SD card: 16GB provides plenty of space

### Performance

- Polling every 3 seconds: Fine on 32-bit
- Print jobs: No difference in speed
- Startup time: Slightly faster than 64-bit

---

## 32-bit Lite Troubleshooting

### Problem: "Python module not found"

```bash
# Make sure you're using the right Python
which python3
# Should be: /usr/bin/python3

# Check Python version (should be 3.9 or later)
python3 --version

# Reinstall pip packages
pip3 install --upgrade --force-reinstall -r requirements-linux.txt
```

### Problem: "Printer not detected" on 32-bit

```bash
# 32-bit detection is the same, but try:
# 1. Unplug Epson USB
# 2. Wait 10 seconds
# 3. Plug back in
# 4. Wait 15 seconds
# 5. Run:
lpstat -p -d

# Restart CUPS if needed
sudo systemctl restart cups
sleep 5
lpstat -p -d
```

### Problem: "Service won't start"

```bash
# Check if service file has correct path
cat /etc/systemd/system/vprint-agent.service | grep ExecStart

# Should show: /usr/bin/python3 /home/pi/print666/print/printer-agent/agent_linux.py

# Restart service
sudo systemctl daemon-reload
sudo systemctl restart vprint-agent

# Check logs
journalctl -u vprint-agent -n 50
```

### Problem: "Out of memory"

```bash
# Check available memory
free -h

# 32-bit Lite should have plenty on Pi Zero W
# If issues, increase swap:
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Change CONF_SWAPSIZE from 100 to 256
sudo dphys-swapfile swapon
```

---

## 32-bit Lite Specific Commands

```bash
# Check OS version
cat /etc/os-release

# Check system architecture (should show ARM)
uname -m

# Check if 32-bit or 64-bit
getconf LONG_BIT
# Output: 32 (confirms 32-bit)

# Check Python architecture
python3 -c "import struct; print(struct.calcsize('P') * 8)"
# Output: 32 (32-bit Python)
```

---

## Memory & CPU Monitoring (32-bit specific)

```bash
# Check memory usage
free -h

# Monitor in real-time
watch -n 1 free -h

# Check CPU temperature (Pi Zero W)
vcgencmd measure_temp

# Check if thermal throttling
vcgencmd get_throttled
# If shows 0x0, no throttling
# If shows 0x1, some throttling occurred

# Check CPU frequency
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
```

---

## Quick Setup Summary for 32-bit Lite

```bash
# 1. Update system
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install CUPS & Epson driver
sudo apt-get install -y cups cups-client printer-driver-escpr libcups2-dev

# 3. Configure CUPS
sudo systemctl start cups && sudo systemctl enable cups
sudo usermod -a -G lpadmin pi && sudo usermod -a -G lp pi

# 4. Install Python tools
sudo apt-get install -y python3 python3-pip git

# 5. Clone repo
git clone https://github.com/YOUR_USER/print666.git
cd print666/print/printer-agent

# 6. Install dependencies
pip3 install -r requirements-linux.txt

# 7. Create .env
cp .env.example .env
nano .env  # Edit with your values

# 8. Test agent
python3 agent_linux.py

# 9. Install service
sudo cp vprint-agent.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent

# 10. Check status
sudo systemctl status vprint-agent
```

**Total setup time: ~45 minutes**

---

## Reboot & Verify (Final Check)

```bash
# Reboot the Pi
sudo reboot

# Wait 30 seconds, then SSH back in
ssh pi@vprint-rpi.local

# Wait another 10 seconds for agent to start
sleep 10

# Check if service auto-started
sudo systemctl status vprint-agent
# Should show "active (running)"

# Verify printer still detected
lpstat -p -d
# Should show Epson_L3210

# Done! 🎉
```

---

## Your Setup is Optimized for 32-bit Lite! ✓

Everything is now configured for **Raspberry Pi OS 32-bit Lite** with your **Epson L3210**.

**The system will:**

- Use minimal memory (32-bit is lighter)
- Run efficiently on Pi Zero W
- Auto-start on power-up
- Poll for jobs every 3 seconds
- Print to Epson L3210 automatically

**No laptop needed ever again!** 🍓🖨️
