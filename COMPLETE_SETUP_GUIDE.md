# VPrint Complete Project Setup Guide

## From Laptop to Raspberry Pi Zero W - Full Integration

---

## Overview: What You Have

Your VPrint project has **3 main parts**:

1. **Frontend Web App** (React, TypeScript, Tailwind CSS)
   - User interface for uploading files and making payments
   - Deployed to Vercel or self-hosted

2. **Backend Server** (Supabase)
   - Database (PostgreSQL)
   - Authentication
   - File storage
   - Edge Functions

3. **Printer Agent** (Python script)
   - Polls Supabase for print jobs
   - Downloads files
   - Sends to physical printer
   - Updates job status

**Current Problem:** Printer agent running on laptop = laptop must always be on

**Solution:** Run Printer Agent on Raspberry Pi Zero W = set it and forget it

---

## Complete Setup Path

```
Your Laptop (Setup Phase)
    ↓
    ├─ Configure Supabase
    ├─ Deploy Frontend App
    └─ Prepare Printer Configuration
    ↓
Raspberry Pi Zero W (Production)
    ├─ Flash OS
    ├─ Install CUPS (Printer Service)
    ├─ Install Python & Agent
    ├─ Configure Environment
    ├─ Set as Auto-start Service
    └─ Monitor & Maintain
```

---

## PHASE 1: Laptop Setup (Do This First)

### Step 1a: Verify Supabase Project

**Login to Supabase:**

1. Go to https://app.supabase.com
2. Open your VPrint project
3. Go to **Settings → API**
4. Copy these values and save them:
   ```
   Project URL: https://YOUR_PROJECT_ID.supabase.co
   Service Role Secret: eyJhbGciOi...
   Anon Public Key: eyJhbGciOi...
   ```

### Step 1b: Add Printer to Database

1. In Supabase, go to **SQL Editor**
2. Run this query to see existing printers:

   ```sql
   SELECT * FROM printers;
   ```

3. If no printers exist, insert one:

   ```sql
   INSERT INTO printers (name, location_id, model, status)
   VALUES ('Raspberry Pi Zero W', 1, 'USB Printer', 'active')
   RETURNING id;
   ```

4. **Copy the returned ID** (this is your PRINTER_ID)

5. Also check locations exist:
   ```sql
   INSERT INTO locations (name, address)
   VALUES ('Main Office', '123 Street')
   RETURNING id;
   ```

### Step 1c: Create First Admin User

1. Go to your deployed VPrint app
2. Click **Admin Dashboard** → **Login**
3. Sign up a new account
4. In Supabase, go to **Authentication → Users**
5. Copy the user's UUID
6. In **SQL Editor**, run:
   ```sql
   INSERT INTO user_roles (user_id, role)
   VALUES ('USER_UUID_HERE', 'admin');
   ```

### Step 1d: Deploy Frontend App

**Option A: Vercel (Recommended)**

1. Push code to GitHub
2. Go to https://vercel.com
3. Import your GitHub repo (`print666`)
4. Add environment variables:
   - `VITE_SUPABASE_URL` = Your Supabase URL
   - `VITE_SUPABASE_PUBLISHABLE_KEY` = Your Anon Key
   - `VITE_RAZORPAY_KEY` = Your Razorpay Public Key
5. Click Deploy
6. Note the deployment URL (e.g., `https://vprint-xxx.vercel.app`)

**Option B: Self-hosted (requires Node.js)**

```bash
cd print
npm install
npm run build
npm run preview  # For local testing, or deploy the dist/ folder
```

**Save your Frontend URL**, you'll use it to test later.

### Step 1e: Test Supabase Connection

On your laptop, test the connection:

```bash
# Navigate to printer-agent folder
cd print/printer-agent

# Create temporary .env for testing
cat > test.env << 'EOF'
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOi...
PRINTER_ID=your-printer-uuid
EOF

# Quick Python test
python3 -c "from supabase import create_client; print('✓ Supabase library works')"
```

**Your Laptop Setup is Complete ✓**

---

## PHASE 2: Raspberry Pi Zero W Hardware Setup

### Step 2a: Prepare SD Card

**What You Need:**

- Raspberry Pi Zero W (with WiFi)
- SD Card (16GB+ recommended)
- Power supply (5V, 2A)
- Computer to flash SD card
- USB Printer

**Flashing Process:**

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Insert SD card into your computer
3. Open Raspberry Pi Imager:
   - **Device**: Raspberry Pi Zero W
   - **OS**: Raspberry Pi OS Lite (64-bit)
   - **Storage**: Your SD card
   - **Settings** (⚙️):
     - Hostname: `vprint-rpi`
     - Enable SSH ✓
     - Username: `pi`
     - Password: Your choice
     - Configure WiFi: Your SSID & password
     - Timezone: Your timezone
4. Click **Write** and wait (~5 minutes)

### Step 2b: Power On & Connect

1. Insert flashed SD card into Raspberry Pi
2. Connect USB printer to Raspberry Pi (or USB hub)
3. Power on Raspberry Pi

### Step 2c: Find Raspberry Pi's IP

On your laptop/phone:

**Windows:**

```powershell
ping vprint-rpi.local
```

**Mac/Linux:**

```bash
ping vprint-rpi.local
```

**Note the IP address** (e.g., `192.168.1.100`)

---

## PHASE 3: Raspberry Pi Software Setup (30 minutes)

### Step 3a: SSH into Raspberry Pi

**Mac/Linux:**

```bash
ssh pi@vprint-rpi.local
# Password: (the one you set during imaging)
```

**Windows (PowerShell):**

```powershell
ssh pi@vprint-rpi.local
# Password: (the one you set during imaging)
```

### Step 3b: Run Automated Setup Script

Once connected via SSH, run:

```bash
# Download the setup script
curl https://raw.githubusercontent.com/YOUR_REPO/print666/main/print/printer-agent/setup_raspberrypi.sh -o setup.sh

# Make it executable
chmod +x setup.sh

# Run the script
./setup.sh
```

**This will automatically:**

- Update system
- Install CUPS (printer service)
- Install Python & dependencies
- Configure permissions
- Create systemd service

### Step 3c: Manual Configuration (if not using script)

If you prefer manual setup, follow these commands:

```bash
# 1. Update system
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install CUPS
sudo apt-get install -y cups cups-client libcups2-dev

# 3. Add pi to printer group
sudo usermod -a -G lpadmin pi

# 4. Start CUPS
sudo systemctl start cups
sudo systemctl enable cups

# 5. Install Python
sudo apt-get install -y python3 python3-pip git

# 6. Clone repository
git clone https://github.com/YOUR_REPO/print666.git

# 7. Navigate to agent folder
cd print666/print/printer-agent

# 8. Install Python packages
pip3 install -r requirements.txt

# 9. Create .env (see next step)
```

### Step 3d: Configure Environment Variables

Create the `.env` file:

```bash
nano .env
```

Paste the following with YOUR actual values:

```env
# From Supabase Dashboard
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# From printers table (UUID you copied earlier)
PRINTER_ID=550e8400-e29b-41d4-a716-446655440000

# Optional: exact printer name (leave blank for default)
PRINTER_NAME=HP_LaserJet_Pro_M404n

# Optional: polling interval in seconds
POLL_INTERVAL=3
```

**Save:** Ctrl+X → Y → Enter

### Step 3e: Test Printer Connection

```bash
# List available printers
lpstat -p -d

# Test print (replace PRINTER_NAME with yours)
echo "Test from Raspberry Pi" | lp -d HP_LaserJet_Pro_M404n

# Check if something printed at the printer
```

### Step 3f: Test Agent Manually

```bash
# Navigate to agent directory
cd ~/print666/print/printer-agent

# Run agent in test mode (Ctrl+C to stop)
python3 agent_linux.py
```

**You should see:**

```
2025-03-02 10:15:30 | INFO     | ==========================================
2025-03-02 10:15:30 | INFO     | VPrint Agent Started (Linux) | Printer: xxxx
2025-03-02 10:15:30 | INFO     | ==========================================
2025-03-02 10:15:31 | INFO     | Initialized API Manager with: https://smartprinter.in/api/jobs
```

**If errors:** See Troubleshooting section below

### Step 3g: Install Systemd Service (Auto-start)

```bash
# Copy service file to system
sudo cp ~/print666/print/printer-agent/vprint-agent.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable to start on boot
sudo systemctl enable vprint-agent

# Start now
sudo systemctl start vprint-agent

# Check status
sudo systemctl status vprint-agent
```

**You should see: "active (running)"**

---

## PHASE 4: End-to-End Testing

Now test the complete workflow!

### Step 4a: Verify Agent is Running

**On Raspberry Pi:**

```bash
sudo systemctl status vprint-agent
```

**Watch logs:**

```bash
sudo journalctl -u vprint-agent -f
```

### Step 4b: Upload a Test Job

1. Go to your Frontend URL (from Phase 1)
2. Click **"Start Printing"**
3. Scan QR code or select printer manually
4. **Upload a PDF** file
5. Set print options (copies, B/W or color)
6. **Make a test payment** (use Razorpay test card)

### Step 4c: Watch the Magic

1. **Monitor Raspberry Pi logs** (in another terminal):

   ```bash
   sudo journalctl -u vprint-agent -f
   ```

2. **You should see:**

   ```
   --- Starting Job: job-uuid ---
   Downloading file...
   Executing print command...
   --- Job job-uuid Completed Successfully ---
   ```

3. **Check physical printer** - Your file should print!

### Step 4d: Check Job Status

On the Frontend app, you should see "Print job completed" notification.

---

## PHASE 5: Production Deployment Checklist

Before declaring success:

```
HARDWARE
[ ] Raspberry Pi Zero W powered on and stable
[ ] USB printer connected and powered on
[ ] WiFi connection stable
[ ] Minimum 90 minutes uptime without errors

SUPABASE
[ ] All environment variables correct
[ ] Printer registered in database
[ ] Admin user created
[ ] Storage bucket configured (print-files)
[ ] RLS policies enabled

PRINTER AGENT
[ ] Agent starts on boot automatically
[ ] Agent runs for 24+ hours without crashing
[ ] Logs are clean (no errors)
[ ] Connects to Supabase successfully
[ ] Polls for jobs every 3 seconds

FRONTEND
[ ] Frontend deployed and accessible
[ ] Payment integration (Razorpay) working
[ ] Can upload files successfully
[ ] Status tracking displays correctly

TESTING
[ ] Test job 1: Single-page B/W print ✓
[ ] Test job 2: Multi-page with copies ✓
[ ] Test job 3: Page range selection ✓
[ ] Test job 4: Color print ✓
[ ] Stress test: 10 jobs in 5 minutes ✓

SECURITY
[ ] .env file permissions: 600 (owner read/write only)
[ ] Service Role key never exposed in logs
[ ] Agent runs as non-root user (pi)
[ ] Backup of .env created and stored safely
```

---

## PHASE 6: Maintenance & Monitoring

### Daily Monitoring

```bash
# Check agent status
sudo systemctl status vprint-agent

# View recent logs
journalctl -u vprint-agent -n 50

# Check printer health
lpstat -p -l

# Monitor resources
free -h
df -h
```

### Weekly Tasks

```bash
# Check for updates
sudo apt-get update
sudo apt-get upgrade

# Review error logs
journalctl -u vprint-agent --since "1 week ago" | grep ERROR

# Restart service proactively (zero downtime between jobs)
sudo systemctl restart vprint-agent
```

### Monthly Maintenance

```bash
# Clean up old logs
sudo journalctl --vacuum=time=30d

# Backup current configuration
cp ~/.env ~/.env.backup.$(date +%Y%m%d)

# Check disk space
df -h

# Update printer drivers if available
sudo apt-get update && sudo apt-get upgrade cups
```

---

## Troubleshooting Guide

### Agent Won't Start

```bash
# Check logs
sudo systemctl status vprint-agent
journalctl -u vprint-agent -n 100

# Common issues:
# 1. .env file not found: cp .env.example .env
# 2. Missing dependencies: pip3 install -r requirements.txt
# 3. Wrong path: verify WorkingDirectory in service file

# Restart
sudo systemctl restart vprint-agent
```

### Printer Not Detected

```bash
# List printers
lpstat -p -d

# If empty, printer may not be connected
# Try:
lsusb  # Check USB devices

# Unplug printer, wait 5 seconds, plug back in
# Wait 15 seconds
lpstat -p -d

# Or configure manually in CUPS
# Open: http://vprint-rpi.local:631
```

### Supabase Connection Error

```bash
# Test internet
ping 8.8.8.8

# Test resolution
nslookup supabase.co

# Check .env credentials
cat .env

# Verify in Python
python3
>>> from supabase import create_client
>>> import os
>>> from dotenv import load_dotenv
>>> load_dotenv()
>>> client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE"))
>>> print(client)
```

### Agent Crashes or Stops

```bash
# Check if systemd auto-restarted it
sudo systemctl status vprint-agent

# If "failed":
journalctl -u vprint-agent --since "10 minutes ago" | head -50

# Common causes:
# 1. Network issue: systemd retries automatically
# 2. Out of memory: check with free -h
# 3. Printer error: check lpstat -p -d

# Force restart
sudo systemctl restart vprint-agent
```

### Jobs Not Processing

```bash
# Verify agent is running
sudo systemctl status vprint-agent

# Check logs for job arrival
journalctl -u vprint-agent -f

# If no jobs: check in Supabase
# Table: print_jobs
# Look for status = 'pending'

# Manual job creation for testing:
# Use Supabase UI or API to insert a test job
```

### Performance Issues

```bash
# Check CPU usage
top -n1 | head -10

# Check memory
free -h

# Check disk
df -h

# Check network
ifconfig

# If issues:
# 1. Reduce POLL_INTERVAL from 3 to 5
# 2. Restart service: sudo systemctl restart vprint-agent
# 3. Check for memory leaks in logs
```

---

## Useful Commands Quick Reference

```bash
# SERVICE MANAGEMENT
sudo systemctl start vprint-agent      # Start service
sudo systemctl stop vprint-agent       # Stop service
sudo systemctl restart vprint-agent    # Restart service
sudo systemctl status vprint-agent     # Check status
sudo systemctl enable vprint-agent     # Enable on boot

# LOGS & DEBUGGING
sudo journalctl -u vprint-agent -f     # Real-time logs
journalctl -u vprint-agent -n 50       # Last 50 lines
journalctl -u vprint-agent --since "1 h ago"  # Last 1 hour

# PRINTER MANAGEMENT
lpstat -p -d                           # List printers
lpstat -p -l                           # Detailed printer info
lsusb                                  # List USB devices
echo "Test" | lp -d PRINTER            # Test print

# SYSTEM INFO
hostname -I                            # Show IP address
free -h                                # Memory usage
df -h                                  # Disk usage
vcgencmd measure_temp                  # CPU temperature
uname -a                               # System info

# SSH REMOTE
ssh pi@vprint-rpi.local               # Connect to Pi
scp file.txt pi@vprint-rpi.local:/tmp # Copy file to Pi
scp pi@vprint-rpi.local:/tmp/file.txt . # Copy from Pi
```

---

## File Structure

```
print666/
└── print/
    ├── printer-agent/
    │   ├── agent.py                          (Windows version)
    │   ├── agent_linux.py                    (Raspberry Pi version) ← USE THIS
    │   ├── requirements.txt
    │   ├── .env                              (create this)
    │   ├── .env.example
    │   ├── vprint-agent.service              (systemd file)
    │   ├── setup_raspberrypi.sh              (automated setup)
    │   ├── RASPBERRY_PI_SETUP_GUIDE.md       (detailed guide)
    │   ├── QUICK_REFERENCE.md                (command reference)
    │   └── logs/
    │       └── agent.log
    ├── src/                                  (Frontend React code)
    ├── package.json
    ├── README.md
    └── ...
```

---

## Support & Troubleshooting Resources

### If Agent Won't Connect

1. Check .env file: `cat ~/.env`
2. Verify WiFi: `hostname -I`
3. Test Supabase: `python3 -c "from supabase import create_client; print('OK')"`
4. Check internet: `ping 8.8.8.8`

### If Printer Won't Print

1. Check connected: `lsusb`
2. Check CUPS: `lpstat -p -d`
3. Manual test: `echo "Test" | lp`
4. Restart CUPS: `sudo systemctl restart cups`

### If Service Won't Start

1. Check logs: `journalctl -u vprint-agent -n 100`
2. Test manually: `python3 agent_linux.py`
3. Fix any errors
4. Restart: `sudo systemctl restart vprint-agent`

### Emergency Commands

```bash
# Stop agent immediately (emergency)
sudo systemctl stop vprint-agent

# Disable auto-start (emergency)
sudo systemctl disable vprint-agent

# Emergency restart system
sudo reboot

# Soft shutdown
sudo shutdown -h now
```

---

## Success Indicators

Your VPrint system is working correctly when:

✓ Agent starts automatically on power-up
✓ Agent process shows "active (running)"
✓ Logs show no errors
✓ Print jobs arrive and process within 10 seconds
✓ Test print job appears at physical printer
✓ Frontend shows job status "Completed"
✓ Printer remains connected 24/7
✓ Service has been running for 7+ days without restart

---

## You're Done! 🎉

Your VPrint printing kiosk is now fully operational on Raspberry Pi Zero W!

**Next Steps:**

1. Let it run for 3-7 days without touching it
2. Monitor logs periodically
3. Test with real print jobs
4. Set up remote monitoring if needed
5. Enjoy hands-off printing!

**Questions?** Check:

1. QUICK_REFERENCE.md for command reminders
2. Troubleshooting section above
3. Check systemd logs: `journalctl -u vprint-agent -f`
4. Review Supabase console for job records

Have fun! 🖨️
