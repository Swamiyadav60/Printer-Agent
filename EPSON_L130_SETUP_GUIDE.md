# Epson L130 Printer Setup for Raspberry Pi Zero W

Complete setup guide specifically for **Epson EcoTank L130** printer with VPrint system.

---

## About Epson L130

**Specifications:**

- **Color**: Color inkjet printer
- **Type**: Single function - Print only (no scan/copy)
- **Connection**: USB only (no WiFi)
- **Default Paper**: A4 (210 x 297 mm)
- **Max Print Speed**: ~27 ppm B&W, ~17 ppm Color (slower than L3210)
- **Print Quality**: 5760 x 1440 dpi
- **EcoTank**: Yes - very low cost per page (~₹0.30)
- **Model Year**: Older model (good for basic printing)

**Linux Support**: Excellent - CUPS has native drivers for Epson printers

**Key Difference from L3210**: L130 is simpler, older model but still works great with Linux!

---

## Step 1: Physical Setup

### 1.1 Connect Printer to Raspberry Pi

1. **Use a USB Hub** (recommended for Pi Zero W)
   - L130 requires stable USB connection
   - Pi Zero W has only one USB port → use powered USB hub
   - Connect hub to Pi, then printer to hub

2. **Power Printer**
   - Turn ON the L130
   - Wait for boot (10-15 seconds)
   - Check for paper and ink levels

### 1.2 Verify USB Connection

On Raspberry Pi, check if printer is detected:

```bash
# List all USB devices
lsusb

# You should see:
# Bus 001 Device 003: ID 04b8:0a37 Seiko Epson Corp. L130 Series
# (Note: L130 ID is 04b8:0a37, different from L3210!)
```

---

## Step 2: Install Epson L130 Drivers on Raspberry Pi (32-bit Lite)

### 2.1 Update System

```bash
# Update system first
sudo apt-get update
sudo apt-get upgrade -y
```

### 2.2 Install CUPS

```bash
# Install CUPS
sudo apt-get install -y cups cups-client libcups2-dev

# Install Epson printer support
sudo apt-get install -y printer-driver-escpr

# Note: For L130, escpr is the correct driver
# Note: printer-driver-escpr2 may not work with L130

# Install additional utilities
sudo apt-get install -y cups-filters cups-bsd
```

### 2.3 Start CUPS Service

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

## Step 3: Detect & Configure Epson L130 in CUPS

### 3.1 Wait for Auto-Detection

```bash
# Wait 15 seconds for printer to be detected
sleep 15

# List printers
lpstat -p -d

# You should see output like:
# printer Epson_L130_Series is idle. enabled since...
```

### 3.2 Get Exact Printer Name

```bash
# List all configured printers with full details
lpstat -p -l

# Example output:
# printer Epson_L130_Series is idle. enabled since Wed 01 Jan 2025 10:00:00 AM UTC
#     Form mounted:
#     Content types: any
#     Printer type: unknown
#     Device URI: usb://SEIKO%20EPSON%20Corp./L130%20Series
```

**Copy the printer name:** `Epson_L130_Series` (or similar)

---

## Step 4: Test Epson L130 Printing

### 4.1 Direct Print Test

```bash
# Create a test file
echo "TEST PRINT FROM RASPBERRY PI - EPSON L130" > test.txt

# Print to Epson L130
# Replace PRINTER_NAME with your actual name from Step 3
lp -d Epson_L130_Series test.txt

# Check job status
lpq -P Epson_L130_Series
```

**Your Epson L130 should print a page with "TEST PRINT FROM RASPBERRY PI - EPSON L130"**

### 4.2 PDF Test Print

```bash
# Print a PDF if you have one
lp -d Epson_L130_Series document.pdf

# Print with 2 copies
lp -n 2 -d Epson_L130_Series document.pdf

# Print page range (pages 1-3)
lp -P 1-3 -d Epson_L130_Series document.pdf
```

### 4.3 Multiple Copies Test

```bash
# Print 3 copies
lp -n 3 -d Epson_L130_Series test.txt

# Verify all 3 pages printed
```

---

## Step 5: Configure VPrint Agent for Epson L130

### 5.1 Update .env File

```bash
nano ~/print666/print/printer-agent/.env
```

**Use these values for Epson L130:**

```env
# Supabase Configuration
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Printer Configuration - EPSON L130
PRINTER_ID=your-printer-uuid-from-supabase
PRINTER_NAME=Epson_L130_Series

# Agent Settings
POLL_INTERVAL=3
```

### 5.2 Register Printer in Supabase

In your Supabase dashboard:

1. Go to **SQL Editor**
2. Run this query:

```sql
-- Check if Epson L130 already registered
SELECT * FROM printers WHERE name LIKE '%L130%';

-- If not exists, insert it
INSERT INTO printers (name, location_id, model, status)
VALUES (
  'Epson L130 - Raspberry Pi',
  1,  -- Replace 1 with your location_id
  'Epson EcoTank L130',
  'active'
)
RETURNING id;
```

3. **Copy the returned `id`** (this is your PRINTER_ID for .env)

---

## Step 6: Complete 32-bit Lite Setup for L130

Follow the same setup as in `SETUP_32BIT_LITE.md` BUT with this change:

**In Step 10 (Configure .env), use:**

```env
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
PRINTER_ID=550e8400-e29b-41d4-a716-446655440000
PRINTER_NAME=Epson_L130_Series
POLL_INTERVAL=3
```

**That's the only difference!** Everything else from `SETUP_32BIT_LITE.md` works the same.

---

## Epson L130 vs L3210 Comparison

| Feature           | L130           | L3210                |
| ----------------- | -------------- | -------------------- |
| Print Speed B&W   | 27 ppm         | 38 ppm               |
| Print Speed Color | 17 ppm         | 38 ppm               |
| print Quality     | 5760x1440 dpi  | 5760x1440 dpi        |
| EcoTank           | Yes            | Yes                  |
| Cost/Page         | ~₹0.30         | ~₹0.50               |
| Linux Driver      | escpr          | escpr                |
| USB Detection     | Yes            | Yes                  |
| Duplex            | No             | No                   |
| Model Type        | Older, simpler | Newer, more features |

**Bottom Line**: L130 works great with Linux! Just slower but cheaper to operate.

---

## Troubleshooting Epson L130

### Problem: Printer Not Detected

```bash
# Check USB connection
lsusb | grep -i epson

# Look for: ID 04b8:0a37 (L130 specific ID)

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

### Problem: "Printer shows error state"

```bash
# Check printer status
lpstat -p -l

# If shows "error" status:
# 1. Turn OFF the L130
# 2. Wait 10 seconds
# 3. Turn ON the L130
# 4. Wait 15 seconds
# 5. Check again: lpstat -p -l
```

### Problem: "Print jobs stuck in queue"

```bash
# Check print queue
lpq -P Epson_L130_Series

# Cancel all jobs
cancel -a

# Cancel specific job (replace 123)
cancel Epson_L130_Series-123

# Remove and re-add printer
sudo lpadmin -x Epson_L130_Series
sudo systemctl restart cups
```

### Problem: Epson L130 Shows as "Idle" But Won't Print

```bash
# Check CUPS error log
sudo tail -f /var/log/cups/error_log

# Common causes:
# 1. Printer is offline: Check USB, power it off/on
# 2. No paper: Add paper to tray
# 3. Ink level low: Check ink on printer display
# 4. Paper jam: Open printer and check

# Try manual print to test
echo "Test" | lp -d Epson_L130_Series
```

---

## Complete Epson L130 + VPrint Setup (Quick Copy-Paste)

```bash
# 1. Update & Install
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y cups cups-client printer-driver-escpr libcups2-dev

# 2. Start CUPS
sudo systemctl start cups && sudo systemctl enable cups
sudo usermod -a -G lpadmin pi && sudo usermod -a -G lp pi

# 3. Check printer (after connecting USB)
sleep 15
lpstat -p -d

# 4. Test print
echo "VPrint Test from Raspberry Pi" | lp -d Epson_L130_Series

# 5. Clone and setup VPrint agent
git clone https://github.com/YOUR_USER/print666.git
cd print666/print/printer-agent
pip3 install -r requirements-linux.txt

# 6. Configure .env
nano .env
# Add:
# PRINTER_NAME=Epson_L130_Series
# PRINTER_ID=(your UUID)
# Etc.

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

## Epson L130 Success Checklist

- [ ] Epson L130 powered on and connected via USB
- [ ] `lsusb` shows Seiko Epson Corp. L130 (ID 04b8:0a37)
- [ ] `lpstat -p -d` shows `Epson_L130_Series`
- [ ] Manual print test successful
- [ ] .env configured with `PRINTER_NAME=Epson_L130_Series`
- [ ] VPrint Agent starts without errors
- [ ] Agent logs show: "Printer: Epson_L130_Series"
- [ ] First test print job via VPrint completed successfully
- [ ] Systemd service auto-starts on boot
- [ ] Stable for 24+ hours without errors

---

## Epson L130 Performance Specs

| Metric                 | Value                           |
| ---------------------- | ------------------------------- |
| Print Speed B&W        | 27 ppm (A4)                     |
| Print Speed Color      | 17 ppm (A4)                     |
| Print Quality          | 5760 x 1440 dpi                 |
| Paper Types            | Plain, Glossy, Fine Art         |
| Paper Sizes            | A4, A5, Letter, envelope        |
| Monthly Duty Cycle     | 5,000 pages                     |
| Estimated Monthly Cost | ~₹0.30/page (ink only, EcoTank) |
| Nozzle Count           | 180 nozzles (fewer than L3210)  |

---

## Your Epson L130 is Ready! ✓

Your EcoTank L130 - the budget-friendly option - is now fully integrated with VPrint on Raspberry Pi Zero W.

**Slower than L3210 but much cheaper to operate!**

The printer will automatically handle all print jobs sent from your kiosk!

---

## Quick Reference Commands for Epson L130

```bash
# List printer
lpstat -p -d

# Print test
echo "Test" | lp -d Epson_L130_Series

# Print file
lp -d Epson_L130_Series /path/to/file.pdf

# Print with copies
lp -n 3 -d Epson_L130_Series file.pdf

# Print page range
lp -P 1-5 -d Epson_L130_Series file.pdf

# Check queue
lpq -P Epson_L130_Series

# Cancel job
cancel Epson_L130_Series-1

# Printer options
lpoptions -p Epson_L130_Series -l

# Printer status
lpstat -p -l

# Restart CUPS
sudo systemctl restart cups
```

---

**Perfect choice for a budget kiosk! The Epson L130 with EcoTank will serve you well! 🎉**
