# Epson L3210 Printer Setup for Raspberry Pi Zero W

Complete setup guide specifically for **Epson EcoTank L3210** printer with VPrint system.

---

## About Epson L3210

**Specifications:**

- **Color**: Color inkjet printer
- **Type**: MFP (Multifunction) - Print, Scan, Copy
- **Connection**: USB only (no WiFi)
- **Default Paper**: A4 (210 x 297 mm)
- **Max Print Speed**: ~38 ppm (pages per minute) B/W, ~38 ppm Color
- **Print Quality**: Suitable for kiosk/self-service printing

**Linux Support**: Excellent - CUPS has native drivers for Epson printers

---

## Step 1: Physical Setup

### 1.1 Connect Printer to Raspberry Pi

1. **Use a USB Hub** (recommended for Pi Zero W)
   - Epson L3210 requires stable USB connection
   - Pi Zero W has only one USB port - use powered USB hub
   - Connect hub to Pi, then printer to hub

2. **Direct USB Connection** (if power-supplied separately)
   - USB-A to USB-B cable (comes with printer)
   - Connect to Pi Zero W's microUSB adapter or via hub

3. **Power Printer**
   - Turn ON the printer
   - Wait for it to fully boot (10-15 seconds)
   - Check for paper and ink levels

### 1.2 Verify USB Connection

On Raspberry Pi, check if printer is detected:

```bash
# List all USB devices
lsusb

# You should see something like:
# Bus 001 Device 003: ID 04b8:0a13 Seiko Epson Corp. L3210 Series
```

**Note the ID:** `04b8:0a13` (Epson vendor ID is `04b8`)

---

## Step 2: Install Epson Drivers on Raspberry Pi

### 2.1 Install CUPS and Epson Support

```bash
# Update system first
sudo apt-get update
sudo apt-get upgrade -y

# Install CUPS
sudo apt-get install -y cups cups-client libcups2-dev

# Install Epson printer support
sudo apt-get install -y printer-driver-escpr
sudo apt-get install -y printer-driver-escpr2

# Alternative: Install all printer drivers
sudo apt-get install -y printer-driver-all

# Install additional utilities
sudo apt-get install -y cups-filters cups-bsd
```

### 2.2 Start CUPS Service

```bash
# Start CUPS daemon
sudo systemctl start cups

# Enable CUPS to start on boot
sudo systemctl enable cups

# Add pi user to printer group
sudo usermod -a -G lpadmin pi
sudo usermod -a -G lp pi

# Restart CUPS to apply permissions
sudo systemctl restart cups
```

---

## Step 3: Detect & Configure Epson L3210 in CUPS

### 3.1 Auto-Detection

```bash
# Wait 10-15 seconds for printer to be detected
# Then list printers
lpstat -p -d

# You should see output like:
# printer Epson_L3210_Series is idle. enabled since...
```

If printer doesn't appear immediately:

```bash
# Restart CUPS
sudo systemctl restart cups

# Wait 5 seconds
sleep 5

# Check again
lpstat -p -d
```

### 3.2 Manual Configuration (if not auto-detected)

**Option A: CUPS Web Interface**

```bash
# Open CUPS admin panel
# Go to: http://vprint-rpi.local:631
# Or: http://192.168.1.X:631 (replace with your Pi's IP)

# Click: Administration → Add Printer
# Select: Epson_L3210_Series (or similar)
# Click: Continue
# Set printer name: Epson_L3210 (no spaces or special chars)
# Click: Continue → Set Default Options
# Choose driver: Epson ESC/P-R
# Click: Add Printer
```

**Option B: Command Line**

```bash
# List available Epson drivers
lpinfo --list-available-devices

# Find your printer (should show something like):
# direct usb://SEIKO%20EPSON%20Corp./L3210%20Series

# Add printer with specific driver
sudo lpadmin -p Epson_L3210 \
  -E \
  -v usb://SEIKO%20EPSON%20Corp./L3210%20Series \
  -m drv:///sample.drv/generic.ppd

# Or use Epson-specific driver
sudo lpadmin -p Epson_L3210 \
  -E \
  -v usb://SEIKO%20EPSON%20Corp./L3210%20Series \
  -m epson-alc3000-series-Epson_ESC_P_R-en.ppd
```

---

## Step 4: Get Exact Printer Name for .env

```bash
# List all configured printers with full details
lpstat -p -l

# Example output:
# printer Epson_L3210 is idle. enabled since Wed 01 Jan 2025 10:00:00 AM UTC
#     Form mounted:
#     Content types: any
#     Printer type: unknown
#     Device URI: usb://SEIKO%20EPSON%20Corp./L3210%20Series
#     On fault: continue
#     After fault delay: 300 seconds
#     Users allowed:
#       (all)
#     Forms allowed:
#       (none)
#     Banner required
#     Job sheets:
#     Character set and stripping:
#     Required operator intervention: none
#     Default options:
```

**Copy the printer name:** `Epson_L3210` (first line after "printer")

---

## Step 5: Test Epson L3210 Printing

### 5.1 Direct Print Test

```bash
# Create a test file
echo "TEST PRINT FROM RASPBERRY PI" > test.txt

# Print to Epson L3210
lp -d Epson_L3210 test.txt

# Check job status
lpq -P Epson_L3210
```

**Your Epson printer should print a page with "TEST PRINT FROM RASPBERRY PI"**

### 5.2 PDF Test Print

```bash
# If you have a PDF, test it
lp -d Epson_L3210 sample.pdf

# Or create a simple PDF using ghostscript
# (if installed)
echo "Hello from VPrint" | enscript -B -p - | ps2pdf - test.pdf
lp -d Epson_L3210 test.pdf
```

### 5.3 Multiple Copies Test

```bash
# Print 3 copies
lp -n 3 -d Epson_L3210 test.txt

# Print with page range (pages 1-2)
lp -P 1-2 -d Epson_L3210 multipage.pdf
```

### 5.4 Color/B&W Test

```bash
# Print in color (default)
lp -d Epson_L3210 colorimage.pdf

# Print in B&W only
lp -o media=A4 -o ColorModel=Gray -d Epson_L3210 document.pdf
```

---

## Step 6: Configure VPrint Agent for Epson L3210

### 6.1 Update .env File

```bash
nano ~/print666/print/printer-agent/.env
```

**Use these values for Epson L3210:**

```env
# Supabase Configuration
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Printer Configuration - EPSON L3210
PRINTER_ID=your-printer-uuid-from-supabase
PRINTER_NAME=Epson_L3210

# Agent Settings
POLL_INTERVAL=3

# Optional: Epson-specific settings
# These are passed to the lp command
```

### 6.2 Register Printer in Supabase

In your Supabase dashboard:

1. Go to **SQL Editor**
2. Run this query:

```sql
-- Check if Epson L3210 already registered
SELECT * FROM printers WHERE name LIKE '%Epson%';

-- If not exists, insert it
INSERT INTO printers (name, location_id, model, status)
VALUES (
  'Epson L3210 - Raspberry Pi',
  1,  -- Replace 1 with your location_id
  'Epson EcoTank L3210',
  'active'
)
RETURNING id;
```

3. **Copy the returned `id`** (this is your PRINTER_ID for .env)

---

## Step 7: Advanced Epson L3210 Print Options

### 7.1 Print Quality Settings

```bash
# High quality print
lp -o media=A4 -o quality=high -d Epson_L3210 document.pdf

# Draft quality (faster)
lp -o media=A4 -o quality=draft -d Epson_L3210 document.pdf

# Photo quality
lp -o media=PhotoGlossy -o quality=photo -d Epson_L3210 photo.pdf
```

### 7.2 Paper Size Options

```bash
# A4 (Default - 210 x 297 mm)
lp -o media=A4 -d Epson_L3210 doc.pdf

# Letter (8.5 x 11 inches)
lp -o media=Letter -d Epson_L3210 doc.pdf

# A5
lp -o media=A5 -d Epson_L3210 doc.pdf

# Envelope
lp -o media=Envelope -d Epson_L3210 doc.pdf

# List all supported media for your printer
lpoptions -p Epson_L3210 -l
```

### 7.3 Duplex Printing (if supported)

```bash
# Check if Epson L3210 has duplex support
# (Note: L3210 does NOT support automatic duplex)

# For manual duplex (user flips paper), use:
lp -o sides=two-sided-short-edge -d Epson_L3210 doc.pdf
```

### 7.4 View All Available Options for Epson L3210

```bash
# List all printer capabilities
lpoptions -p Epson_L3210 -l

# Output will show something like:
# ColorModel/Color Model: *RGB RGBA
# Duplex/Double-Sided: None *DuplexNoTumble
# MediaType/Media Type: *Auto Envelope Fine Glossy ...
# Quality/Output Quality: *Normal High Draft
# ...
```

---

## Step 8: Troubleshooting Epson L3210

### Problem: Printer Not Detected

```bash
# Check USB connection
lsusb | grep -i epson

# If not showing:
# 1. Unplug USB cable
# 2. Restart Raspberry Pi: sudo reboot
# 3. Wait 30 seconds
# 4. Plug USB back in
# 5. Wait 15 seconds
# 6. Run: lpstat -p -d

# If still not detected:
sudo systemctl restart cups
sleep 10
lsusb
```

### Problem: Printer Shows Error State

```bash
# Check printer status
lpstat -p -l

# If shows "error" status, reset printer:
# 1. Turn OFF the printer
# 2. Wait 10 seconds
# 3. Turn ON the printer
# 4. Wait 15 seconds
# 5. Check again: lpstat -p -l

# Or restart CUPS
sudo systemctl restart cups
```

### Problem: Print Jobs Stuck in Queue

```bash
# Check print queue
lpq -P Epson_L3210

# Cancel all jobs
cancel -a

# Cancel specific job (replace 123 with job number)
cancel Epson_L3210-123

# Remove printer and re-add
sudo lpadmin -x Epson_L3210
sudo systemctl restart cups
```

### Problem: Epson L3210 Shows as "Idle" But Won't Print

```bash
# Check CUPS error log
sudo tail -f /var/log/cups/error_log

# Common causes:
# 1. Printer is offline: Check USB, power it off/on
# 2. No paper: Add paper to tray
# 3. Ink level low: Check ink levels on printer display
# 4. Paper jam: Open printer and check

# Try manual print to test
echo "Test" | lp -d Epson_L3210
```

### Problem: Wrong Print Quality or Colors

```bash
# Set default print quality for Epson L3210
sudo lpadmin -p Epson_L3210 -o quality=high

# Test print
echo "Quality Test" | lp -d Epson_L3210

# To change quality for specific job:
lp -o quality=high -d Epson_L3210 document.pdf
```

---

## Step 9: Epson L3210 Daily Maintenance

### Check Ink/Paper Levels

```bash
# No direct command, but check printer:
# 1. Look at printer display panel
# 2. Check ink level indicator on printer
# 3. Add paper if needed

# Check via CUPS (may show some info)
lpstat -p -l | grep Epson_L3210
```

### Clean Printer Heads (Monthly)

```bash
# On the Epson L3210 printer itself:
# 1. Press the Menu button
# 2. Select "Maintenance"
# 3. Select "Head Cleaning"
# 4. Follow on-screen prompts
```

### Remove Paper Jams

```bash
# If printer shows error:
# 1. Power OFF the printer
# 2. Open the front cover
# 3. Remove any paper inside
# 4. Close cover
# 5. Power ON
# 6. Wait 15 seconds

# Check status
lpstat -p -d
```

---

## VPrint Agent with Epson L3210

Once everything is tested, your VPrint Agent will:

1. **Poll Supabase** for print jobs assigned to `Epson_L3210`
2. **Download PDF files** from Supabase storage
3. **Execute command:** `lp -n COPIES -P RANGE -d Epson_L3210 /tmp/vprint_*.pdf`
4. **Track job status** in real-time
5. **Handle errors** gracefully

### Example Job Flow

```
User uploads PDF → Payment confirmed → Job inserted in Supabase
                              ↓
         Agent detects job (polls every 3 seconds)
                              ↓
    Agent marks job as "processing"
                              ↓
    Agent downloads PDF from storage
                              ↓
    Agent executes:
    lp -n 1 -d Epson_L3210 /tmp/vprint_abc123.pdf
                              ↓
    Epson L3210 prints the document
                              ↓
    Agent marks job as "completed"
                              ↓
User sees "Print Completed" notification on frontend
```

---

## Complete Epson L3210 + VPrint Setup Commands (Quick Copy-Paste)

```bash
# 1. Update & Install
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y cups cups-client printer-driver-escpr printer-driver-escpr2

# 2. Start CUPS
sudo systemctl start cups && sudo systemctl enable cups
sudo usermod -a -G lpadmin pi && sudo usermod -a -G lp pi

# 3. Check printer (after connecting USB)
sleep 15
lpstat -p -d

# 4. Test print
echo "VPrint Test from Raspberry Pi" | lp -d Epson_L3210

# 5. Clone and setup VPrint agent
git clone https://github.com/YOUR_USER/print666.git
cd print666/print/printer-agent
pip3 install -r requirements-linux.txt

# 6. Configure .env
nano .env
# Add: PRINTER_NAME=Epson_L3210

# 7. Test agent
python3 agent_linux.py

# 8. Install as service
sudo cp vprint-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent

# 9. Verify
sudo systemctl status vprint-agent
sudo journalctl -u vprint-agent -f
```

---

## Epson L3210 Performance Specs

| Metric                 | Value                                 |
| ---------------------- | ------------------------------------- |
| Print Speed B&W        | 38 ppm (A4)                           |
| Print Speed Color      | 38 ppm (A4)                           |
| Print Quality          | 5760 x 1440 dpi                       |
| Paper Types            | Plain, Glossy, Fine Art, Envelope     |
| Paper Sizes            | A4, A5, Letter, half-letter, envelope |
| Max Job Size           | Unlimited                             |
| Duplex Support         | Manual only                           |
| Monthly Duty Cycle     | 5,000 pages                           |
| Estimated Monthly Cost | ~₹1 (ink only, EcoTank)               |

---

## Success Checklist for Epson L3210

- [ ] Epson L3210 powered on and connected via USB
- [ ] `lsusb` shows Seiko Epson Corp. L3210
- [ ] `lpstat -p -d` shows `Epson_L3210`
- [ ] Manual print test successful: `echo "Test" | lp -d Epson_L3210`
- [ ] .env configured with `PRINTER_NAME=Epson_L3210`
- [ ] VPrint Agent starts without errors
- [ ] Agent logs show: "Printer: Epson_L3210"
- [ ] First test print job via VPrint completed successfully
- [ ] Systemd service auto-starts on boot
- [ ] Stable for 24+ hours without errors

---

## Your Epson L3210 is Ready! ✓

Your Epson EcoTank L3210 is now fully integrated with VPrint on Raspberry Pi Zero W.

The printer will automatically handle all print jobs sent from your kiosk!

---

## Reference Commands for Epson L3210

```bash
# List printer
lpstat -p -d

# Print test
echo "Test" | lp -d Epson_L3210

# Print file
lp -d Epson_L3210 /path/to/file.pdf

# Print with copies
lp -n 3 -d Epson_L3210 file.pdf

# Print page range
lp -P 1-5 -d Epson_L3210 file.pdf

# Print in B&W
lp -o ColorModel=Gray -d Epson_L3210 file.pdf

# Check queue
lpq -P Epson_L3210

# Cancel job
cancel Epson_L3210-1

# Printer options
lpoptions -p Epson_L3210 -l

# Printer status
lpstat -p -l

# Restart CUPS
sudo systemctl restart cups
```

---

Great choice! The Epson L3210 with its EcoTank system is perfect for a kiosk - very low per-page cost and reliable printing. You're all set! 🎉
