# VPrint + Raspberry Pi Zero W + Epson L3210

## 5-Minute Quick Start (Copy-Paste Commands)

---

## BEFORE YOU START

Save these values from Supabase:

```
SUPABASE_URL = https://your-id.supabase.co
SUPABASE_SERVICE_ROLE = eyJhbGci...
PRINTER_ID = (UUID from database)
```

And add Epson L3210 to printers table:

```sql
INSERT INTO printers (name, location_id, model, status)
VALUES ('Epson L3210', 1, 'Epson EcoTank L3210', 'active')
RETURNING id;  -- COPY THIS ID → PRINTER_ID
```

---

## STEP 1: FLASH RASPBERRY PI (10 minutes, on your laptop)

1. Download: https://www.raspberrypi.com/software/
2. Choose Device: Raspberry Pi Zero W
3. Choose OS: Raspberry Pi OS Lite (64-bit)
4. Choose Storage: Your SD card
5. Settings ⚙️:
   - Hostname: `vprint-rpi`
   - SSH: Enable
   - Username: `pi`
   - Password: your choice
   - WiFi: your network
   - Timezone: your timezone
6. **Write** → Done!

**Then:**

- Insert SD card into Pi
- Connect USB hub to Pi
- Connect Epson L3210 to hub
- Power on Pi
- Power on Epson

---

## STEP 2: CONNECT TO RASPBERRY PI (SSH)

```bash
# From your laptop, Mac, or PC:
ssh pi@vprint-rpi.local

# Password: (what you set above)
```

---

## STEP 3: QUICK AUTOMATED SETUP (copy-paste all at once)

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install CUPS & Epson drivers
sudo apt-get install -y cups cups-client printer-driver-escpr printer-driver-escpr2 libcups2-dev python3 python3-pip git

# Configure CUPS & permissions
sudo systemctl start cups
sudo systemctl enable cups
sudo usermod -a -G lpadmin pi
sudo usermod -a -G lp pi
sudo systemctl restart cups

# Wait 15 seconds for printer detection
sleep 15

# Verify Epson L3210 detected
lpstat -p -d

# Test print to Epson
echo "VPrint Test" | lp -d Epson_L3210
```

**At Epson printer - you should see 1 test page printed!**

---

## STEP 4: CLONE & SETUP VPRINT

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/print666.git

# Navigate to agent
cd print666/print/printer-agent

# Install Python dependencies
pip3 install -r requirements-linux.txt

# Create .env with YOUR values
cat > .env << 'EOF'
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
PRINTER_ID=550e8400-e29b-41d4-a716-446655440000
PRINTER_NAME=Epson_L3210
POLL_INTERVAL=3
EOF

# Test the agent (press Ctrl+C after 10 seconds)
python3 agent_linux.py
```

**You should see:**

```
VPrint Agent Started (Linux)
Initialized API Manager...
Sending GET request...
```

---

## STEP 5: ENABLE AUTO-START

```bash
# Install systemd service
sudo cp vprint-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent

# Verify it's running
sudo systemctl status vprint-agent

# Watch logs
sudo journalctl -u vprint-agent -f
```

**You should see: "active (running)"**

---

## STEP 6: TEST END-TO-END

1. Open your frontend: `https://your-vprint.vercel.app`
2. Click **"Start Printing"**
3. Upload PDF file
4. Click **"Continue"**
5. Set options (1 copy, all pages)
6. Make payment (test card: 4111 1111 1111 1111)

**On Raspberry Pi terminal:**

```bash
# Watch real-time logs
sudo journalctl -u vprint-agent -f
```

**You should see:**

```
--- Starting Job: xxxx ---
Downloading file...
Executing print command: lp -d Epson_L3210 /tmp/vprint_xxx.pdf
--- Job xxxx Completed Successfully ---
```

**At Epson printer - your uploaded PDF should print!**

---

## THAT'S IT! ✓

Your VPrint system is now live!

### Verify with These Commands:

```bash
# Agent running?
sudo systemctl status vprint-agent

# Printer connected?
lpstat -p -d

# Logs clean?
sudo journalctl -u vprint-agent -n 20
```

---

## COMMON COMMANDS (Save This!)

```bash
# View logs
sudo journalctl -u vprint-agent -f

# Restart agent
sudo systemctl restart vprint-agent

# Stop agent (emergency)
sudo systemctl stop vprint-agent

# Check printer
lpstat -p -d

# Test print
echo "Test" | lp -d Epson_L3210

# Copy files to Pi
scp file.txt pi@vprint-rpi.local:/tmp

# Reboot Pi
sudo reboot
```

---

## IF SOMETHING GOES WRONG

**Printer not detected:**

```bash
# 1. Unplug Epson
# 2. Wait 10 seconds
# 3. Plug back in
# 4. Wait 15 seconds
# 5. Run:
lpstat -p -d
```

**Agent not starting:**

```bash
# Check logs:
sudo journalctl -u vprint-agent -n 100

# Test manually:
python3 agent_linux.py
```

**Connection issues:**

```bash
# Check WiFi:
hostname -I

# Check internet:
ping 8.8.8.8

# Check Supabase:
python3 -c "from supabase import create_client; print('OK')"
```

---

## WHAT'S RUNNING

```
Your System:
├─ Raspberry Pi Zero W (connected to WiFi)
│  └─ Epson L3210 (connected via USB)
│      └─ Polling Supabase every 3 seconds
└─ When print job arrives:
   ├─ Download PDF from Supabase storage
   ├─ Send to Epson L3210
   └─ User sees "Completed" on frontend
```

---

## FUTURE COMMANDS YOU MIGHT NEED

```bash
# Update agent code:
cd ~/print666 && git pull && sudo systemctl restart vprint-agent

# Check disk space:
df -h

# Check memory:
free -h

# Update system:
sudo apt-get update && sudo apt-get upgrade -y

# View printer options:
lpoptions -p Epson_L3210 -l

# Print with specific options:
lp -n 3 -P 1-5 -d Epson_L3210 file.pdf
```

---

## DOCUMENTATIONS AVAILABLE

Read these files in `printer-agent/` folder if you need details:

- `FINAL_INTEGRATION_SUMMARY.md` - Complete overview ⭐
- `COMPLETE_SETUP_GUIDE.md` - Detailed step-by-step
- `RASPBERRY_PI_SETUP_GUIDE.md` - Pi-specific details
- `EPSON_L3210_SETUP_GUIDE.md` - Your printer guide ⭐
- `QUICK_REFERENCE.md` - Command reference
- `README_LINUX.md` - Agent documentation

---

**You're done! No laptop needed anymore. Enjoy your kiosk! 🎉**

Questions? Check the documentation files above!
