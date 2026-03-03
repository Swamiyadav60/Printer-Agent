# VPrint Raspberry Pi Zero W Setup Guide

Complete step-by-step guide to set up VPrint printer agent on Raspberry Pi Zero W without any laptop setup.

---

## Part 1: Prerequisites & What You'll Need

### Hardware Required

- **Raspberry Pi Zero W** (with WiFi, not just regular Pi Zero)
- **Power supply** (5V, 2A minimum via micro-USB)
- **SD Card** (16GB or larger, recommended Class 10)
- **USB printer** (connected to Raspberry Pi)
- **WiFi network** (Pi Zero W needs internet connection)

### Software & Accounts

- Supabase account with project already set up (from your laptop)
- Razorpay account (already configured)
- Any computer to initially flash the SD card

---

## Part 2: Prepare Supabase Information

**Do this on your laptop first:**

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Select your VPrint project
3. Go to **Settings → API**
4. Copy and save these values:
   - **Supabase URL** (Project URL)
   - **Service Role Secret** (KEEP THIS SECRET - this is your `SUPABASE_SERVICE_ROLE`)
   - **Anon Public Key** (for reference only)

5. Go to **Database → Printers table** and add your printer:
   - Click "Insert Row"
   - Fill in:
     - **name**: "RPi Zero Printer" (or any name)
     - **location_id**: Select an existing location or create new
     - **model**: "USB Printer on Raspberry Pi"
     - **status**: "active"
   - **Copy the UUID** of this printer (it will be auto-generated)

You'll need these three values for Raspberry Pi setup:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE`
- `PRINTER_ID` (the UUID from the printers table)

---

## Part 3: Flash Raspberry Pi OS to SD Card

### On your computer:

1. **Download Raspberry Pi Imager**
   - [https://www.raspberrypi.com/software/](https://www.raspberrypi.com/software/)
   - Choose for Windows/Mac/Linux

2. **Insert SD Card** into your computer

3. **Open Raspberry Pi Imager** and:
   - Click **Choose Device** → Select "Raspberry Pi Zero W"
   - Click **Choose OS** → Select "Raspberry Pi OS Lite (64-bit)" (lighter weight)
   - Click **Choose Storage** → Select your SD card
   - Click **Settings** (gear icon)
     - Set hostname: `vprint-rpi`
     - Enable SSH: Click toggle → Use password authentication
     - Set username: `pi`
     - Set password: Your choice (e.g., `vprint123`)
     - Configure WiFi: Enter your WiFi SSID and password
     - Set locale & timezone
   - Click **Save** → **Write**
   - Wait for flashing to complete (~5 minutes)

4. **Eject SD Card** and insert into Raspberry Pi Zero W

5. **Power on Raspberry Pi** with power supply connected

---

## Part 4: Connect to Raspberry Pi & Install Software

### Find Raspberry Pi's IP Address

**Option A: From your router**

- Log into router admin panel
- Look for connected devices
- Find `vprint-rpi` device and note its IP (e.g., `192.168.1.100`)

**Option B: Using SSH from computer**

```bash
# Windows (Command Prompt or PowerShell)
ping vprint-rpi.local

# Mac/Linux
ping vprint-rpi.local
```

Note the IP address shown.

### SSH into Raspberry Pi

**Windows (PowerShell):**

```powershell
ssh pi@vprint-rpi.local
# Password: (enter the password you set during imaging)
```

**Mac/Linux (Terminal):**

```bash
ssh pi@vprint-rpi.local
# Password: (enter the password you set during imaging)
```

---

## Part 5: Set Up Printer on Raspberry Pi

Once connected via SSH, run these commands:

### 1. Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### 2. Install CUPS (Common Unix Printing System)

```bash
sudo apt-get install -y cups cups-client
```

### 3. Add pi user to printer group

```bash
sudo usermod -a -G lpadmin pi
```

### 4. Start CUPS service and enable auto-start

```bash
sudo systemctl start cups
sudo systemctl enable cups
```

### 5. Configure USB Printer

**Plug your USB printer into the Raspberry Pi** (or USB hub if needed)

```bash
# List connected printers
lpstat -p -d

# Or check connected USB devices
lsusb
```

**Wait 10-15 seconds** for CUPS to auto-detect the printer.

```bash
# Check printer status
lpstat -p -d

# Full printer details
lpstat -p -l
```

**Note the printer name** (usually something like `HP_LaserJet_Pro_M404n` or similar)

### 6. Test Printer Connection

```bash
# Print a test page
echo "Test Print from Raspberry Pi" | lp -d PRINTER_NAME

# Replace PRINTER_NAME with actual name from above
# Example: lp -d HP_LaserJet_Pro_M404n
```

**Check if printer printed a test page.**

---

## Part 6: Install Python & Dependencies

```bash
# Install Python and pip
sudo apt-get install -y python3 python3-pip

# Install git (for easy cloning)
sudo apt-get install -y git

# Install additional dependencies
sudo apt-get install -y libcups2-dev
```

---

## Part 7: Clone VPrint Project & Set Up Agent

```bash
# Navigate to home directory
cd ~

# Clone your project (replace with your actual git URL)
git clone https://github.com/YOUR_USERNAME/print666.git
cd print666/print/printer-agent

# Install Python dependencies
pip3 install -r requirements.txt
```

### Update Requirements for Linux

Edit `requirements.txt` and remove the Windows-specific dependency:

```bash
nano requirements.txt
```

**Remove or comment out these lines:**

- `pywin32`

**Keep these:**

- `requests`
- `python-dotenv`
- `supabase`
- `pypdf`

Save and exit (Ctrl+X, then Y, then Enter)

**Reinstall with updated requirements:**

```bash
pip3 install -r requirements.txt
```

---

## Part 8: Configure Environment Variables

```bash
# Create .env file
nano .env
```

**Paste the following (replace with your actual values):**

```env
# Supabase Configuration (from Part 2)
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Printer Configuration
PRINTER_ID=uuid-of-your-printer-from-supabase
PRINTER_NAME=HP_LaserJet_Pro_M404n

# Optional: Polling interval in seconds (default: 3)
POLL_INTERVAL=3

# Optional: Custom API URL (leave blank to use default)
# BACKEND_API_URL=https://smartprinter.in/api/jobs
```

**Save and exit** (Ctrl+X, then Y, then Enter)

---

## Part 9: Run Agent in Foreground (Test)

```bash
# Navigate to printer-agent directory
cd ~/print666/print/printer-agent

# Run the Linux version of the agent
python3 agent_linux.py
```

**You should see:**

```
2025-03-02 10:15:30 | INFO     | ==========================================
2025-03-02 10:15:30 | INFO     | VPrint Agent Started (Linux) | Printer: xxxx
2025-03-02 10:15:30 | INFO     | ==========================================
2025-03-02 10:15:31 | INFO     | Initialized API Manager with: https://smartprinter.in/api/jobs
2025-03-02 10:15:32 | INFO     | Sending GET request to: https://smartprinter.in/api/jobs?printer_id=xxxx
```

**If you see errors:**

- Check internet connection: `ping google.com`
- Check Supabase credentials in .env
- Check printer status: `lpstat -p -d`

**To stop the agent**, press Ctrl+C

---

## Part 10: Set Up Automatic Startup with systemd

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/vprint-agent.service
```

**Paste the following:**

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

# Output to syslog
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Save and exit** (Ctrl+X, then Y, then Enter)

### Enable the service to auto-start:

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable vprint-agent

# Start the service now
sudo systemctl start vprint-agent

# Check status
sudo systemctl status vprint-agent
```

**You should see "active (running)"**

### View logs:

```bash
# Real-time logs
sudo journalctl -u vprint-agent -f

# Last 50 lines of logs
journalctl -u vprint-agent -n 50
```

Press Ctrl+C to exit logs.

---

## Part 11: Deploy Frontend Web App (On Laptop)

The VPrint web app needs to be deployed somewhere. Options:

### Option A: Vercel (Recommended - Free)

1. Push your code to GitHub
2. Go to [Vercel](https://vercel.com/)
3. Click "New Project"
4. Import your GitHub repo
5. Set environment variables:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_PUBLISHABLE_KEY`
   - `VITE_RAZORPAY_KEY`
6. Click Deploy

Your app will be live at a URL like `https://vprint-xxx.vercel.app`

### Option B: Self-hosted on Raspberry Pi

If you want to host on the same Pi:

```bash
# Install Node.js and npm
curl -sL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Navigate to project
cd ~/print666/print

# Install dependencies
npm install

# Build for production
npm run build

# Serve with a simple HTTP server
sudo npm install -g serve
serve -s dist -l 3000
```

Access at: `http://vprint-rpi.local:3000`

---

## Part 12: Verify Everything Works

### On your phone or computer:

1. Go to your deployed VPrint app (Vercel URL or Pi IP)
2. Click **"Start Printing"**
3. **Scan the QR code** for your printer (or manually select printer)
4. **Upload a PDF file**
5. **Configure print settings** (copies, page range, color)
6. **Make payment**
7. **Check printer** - Job should print within 10 seconds!

### On Raspberry Pi (check logs):

```bash
# Watch real-time logs
sudo journalctl -u vprint-agent -f
```

You should see:

```
--- Starting Job: xxxx ---
Sending POST request...
Downloading file...
Printing: /tmp/vprint_xxxx.pdf | Copies: 1
Executing print command...
--- Job xxxx Completed Successfully ---
```

---

## Part 13: Troubleshooting

### Problem: Agent won't start

```bash
# Check service status
sudo systemctl status vprint-agent

# Restart service
sudo systemctl restart vprint-agent

# Check full error logs
journalctl -u vprint-agent -n 100
```

### Problem: Printer not detected

```bash
# List all printers
lpstat -p -d

# If printer not showing:
# 1. Unplug USB printer
# 2. Wait 5 seconds
# 3. Plug back in
# 4. Wait 15 seconds
# 5. Run: lpstat -p -d

# If still not showing, check USB
lsusb
```

### Problem: Can't connect to Supabase

```bash
# Test internet connection
ping 8.8.8.8

# Check if .env has correct credentials
cat .env

# Test Supabase connection manually
python3
>>> from supabase import create_client
>>> client = create_client("YOUR_URL", "YOUR_KEY")
>>> print(client)
```

### Problem: Jobs not printing

```bash
# Check if agent is running
sudo systemctl status vprint-agent

# Check if printer is ready
lpstat -p -d

# Test manual print
echo "Test" | lp -d PRINTER_NAME

# Force-restart agent
sudo systemctl restart vprint-agent
```

### Problem: Permission denied errors

```bash
# Ensure pi user is in lpadmin group
groups pi

# If not in lpadmin, add it:
sudo usermod -a -G lpadmin pi

# Restart CUPS
sudo systemctl restart cups
```

---

## Part 14: Maintenance & Updates

### View agent logs

```bash
# Last hour of logs
journalctl -u vprint-agent --since "1 hour ago"

# Last 24 hours
journalctl -u vprint-agent --since "24 hours ago"

# All logs for today
journalctl -u vprint-agent --since today
```

### Update the agent code

```bash
# Navigate to project
cd ~/print666

# Pull latest changes
git pull origin main

# Restart service
sudo systemctl restart vprint-agent
```

### Backup your configuration

```bash
# Backup .env file
cp ~/print666/print/printer-agent/.env ~/print_agent_backup.env

# Keep this safe! It contains sensitive credentials
```

---

## Part 15: Production Checklist

Before going live:

- [ ] Raspberry Pi connected to stable WiFi
- [ ] Printer is powered on and connected via USB
- [ ] Supabase project is configured correctly
- [ ] Admin user created in Supabase
- [ ] Frontend deployed (Vercel or self-hosted)
- [ ] Test print job completed successfully
- [ ] Agent logs are clean (no errors)
- [ ] Service set to auto-start with systemd
- [ ] Backed up .env file in safe location
- [ ] Tested with multiple print jobs
- [ ] Monitor logs for 24 hours for stability

---

## Support Commands Summary

```bash
# Check if agent is running
sudo systemctl status vprint-agent

# Restart agent
sudo systemctl restart vprint-agent

# View real-time logs
sudo journalctl -u vprint-agent -f

# Check printer status
lpstat -p -d

# Test printer
echo "Test" | lp -d YOUR_PRINTER_NAME

# Reload config (if you edit .env)
sudo systemctl restart vprint-agent

# See if Pi is connected to WiFi
ifconfig

# Restart networking
sudo systemctl restart networking
```

---

## Emergency: Disable Auto-start

If agent is causing issues:

```bash
# Disable auto-start
sudo systemctl disable vprint-agent

# Reboot Pi
sudo reboot

# Later, to re-enable:
sudo systemctl enable vprint-agent
```

---

**Congratulations! Your VPrint system is now running on Raspberry Pi Zero W! 🎉**

No laptop needed anymore. The Pi will continuously poll Supabase for print jobs and handle printing automatically.

Any issues? Check the troubleshooting section above first!
