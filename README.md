# VPrint Printer Agent

Production-ready printer agent for **Windows, Linux (Raspberry Pi), and macOS** systems.

> **🆕 NEW**: Raspberry Pi 3B+ Support! See [README-RPI.md](README-RPI.md) for complete setup guide with CUPS + Canon GutePrint drivers.

## Overview

This agent runs on a computer connected to a physical printer. It:

1. Reports its status to the VPrint backend (every 5 seconds)
2. Polls for paid print jobs from Supabase (every 3 seconds)
3. Downloads and prints documents automatically
4. Converts documents if needed (Images → PDF, DOCX/PPTX → PDF)
5. Updates job status in real-time
6. Handles errors gracefully with retry logic

## Platform-Specific Guides

- **🍓 [Raspberry Pi 3B+](README-RPI.md)** - Complete setup with CUPS + Canon GutePrint
- **🪟 Windows** - Continue reading this section
- **🐧 Linux/Ubuntu** - Similar to Raspberry Pi guide
- **🍎 macOS** - Similar to Linux guide

---

## Windows Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
# Or manually:
pip install requests python-dotenv supabase pywin32 Pillow
```

### 2. Register the Printer

1. Open VPrint on your phone
2. Click "Start Printing"
3. Scan the QR code on the printer (or enter a new UUID)
4. The printer will be auto-registered in the database

### 3. Configure the Agent

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE=your_service_role_key_here
PRINTER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PRINTER_NAME=your-printer-name
```

**How to get these values:**

- `SUPABASE_URL`: Supabase Dashboard → Project Settings → API → Project URL
- `SUPABASE_SERVICE_ROLE`: Supabase Dashboard → Project Settings → API → Service Role Secret
- `PRINTER_ID`: VPrint Admin Dashboard → Printers section
- `PRINTER_NAME`: Windows Settings → Devices → Printers & Scanners (printer name)

### 4. Run the Agent

```bash
python agent-rpi.py
# Or for legacy Windows-only version:
python agent.py
```

Expected output:

```
2026-04-08 10:30:45 | INFO     | Starting VPrint Agent on Windows
2026-04-08 10:30:45 | INFO     | VPrint Agent Started on Windows
2026-04-08 10:30:46 | INFO     | Heartbeat started
```

Press `Ctrl+C` to stop.

---

## Raspberry Pi 3B+ Setup (Recommended)

> **For detailed Raspberry Pi setup including CUPS, Canon GutePrint, and systemd service, see [README-RPI.md](README-RPI.md)**

Quick summary:

```bash
# 1. Download setup script
wget https://your-repo/printer-agent/setup-rpi.sh
chmod +x setup-rpi.sh

# 2. Run automated setup
sudo ./setup-rpi.sh

# 3. Configure credentials
sudo nano /home/pi/vprint/.env

# 4. Add printer via CUPS
# Web: http://raspberrypi.local:631
# Or see README-RPI.md for command-line setup

# 5. Start agent
sudo systemctl start vprint-agent

# 6. View logs
sudo journalctl -u vprint-agent -f
```

---

## Environment Variables

See [.env.example](.env.example) for detailed descriptions.

| Variable                | Required | Default | Description                                        |
| ----------------------- | -------- | ------- | -------------------------------------------------- |
| `SUPABASE_URL`          | ✓ Yes    | -       | Supabase project URL (`https://xxxxx.supabase.co`) |
| `SUPABASE_SERVICE_ROLE` | ✓ Yes    | -       | Service role key (SECRET - keep private!)          |
| `PRINTER_ID`            | ✓ Yes    | -       | UUID of the printer in VPrint system               |
| `PRINTER_NAME`          | ✓ Yes    | -       | CUPS printer name (e.g., `canon-printer-1`)        |
| `POLL_INTERVAL`         | No       | `3`     | Seconds between job polls (1-60)                   |
| `HEARTBEAT_INTERVAL`    | No       | `5`     | Seconds between status updates (1-60)              |

#### How to Get Values:

```bash
# 1. Get SUPABASE_URL and SUPABASE_SERVICE_ROLE
# → Supabase Dashboard → Project Settings → API
# → Copy "Project URL" and "Service Role Secret"

# 2. Get PRINTER_ID
# → VPrint Admin Dashboard → Printers section
# Or query: SELECT id FROM printers;

# 3. Get PRINTER_NAME (Raspberry Pi)
lpstat -d -p
# Example output: system default printer: canon-printer-1
```

---

## How It Works

The agent operates in a continuous loop:

```
┌─────────────────────────────────────────────────────────┐
│ 1. STARTUP                                               │
│    • Load environment variables (.env)                  │
│    • Connect to Supabase                                │
│    • Start heartbeat thread (reports "online" status)   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. MAIN POLLING LOOP (every POLL_INTERVAL seconds)      │
│    • Query: Jobs where printer_id=THIS & status=queued  │
│    • If found: Lock job by updating status→"printing"   │
│    • Else: Wait POLL_INTERVAL seconds, try again        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. PROCESS JOB                                          │
│    • Download file from Supabase storage               │
│    • Convert if needed (IMG→PDF, DOCX→PDF, PPTX→PDF) │
│    • Send to local printer via OS command              │
│    • Update status→"completed" or "failed"             │
│    • Clean up temporary files                          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 4. HEARTBEAT THREAD (every HEARTBEAT_INTERVAL seconds)  │
│    • Update printer status in Supabase                  │
│    • Report "online", "busy", or error state            │
│    • Send last_seen timestamp                           │
└─────────────────────────────────────────────────────────┘
```

---

## File Format Support

| Format                | Windows | Linux/RPi | macOS | Conversion Method      |
| --------------------- | ------- | --------- | ----- | ---------------------- |
| **PDF**               | ✓       | ✓         | ✓     | Direct (no conversion) |
| **Images**            | ✓       | ✓         | ✓     | PIL/Pillow → PDF       |
| (JPG, PNG, BMP, WebP) |
| **DOCX**              | ✓       | ✓         | ✓     | Pandoc → PDF           |
| **PPTX**              | ✓       | ✓         | ✓     | Pandoc → PDF           |

---

## Device-Specific Details

### Windows

- **Print Command**: SumatraPDF.exe with `-print-to` flag
- **Printer Enum**: `win32print.EnumPrinters()`
- **File Conversion**: Pandoc CLI or COM objects

### Linux / Raspberry Pi 3B+

- **Print Command**: CUPS `lp` command
- **Printer Enum**: `lpstat -p -d`
- **File Conversion**: Pandoc CLI
- **Requires**: CUPS, Gutenprint (Canon support)
- **Setup Guide**: [README-RPI.md](README-RPI.md)

### macOS

- **Print Command**: CUPS `lp` command
- **Printer Enum**: `lpstat -p -d`
- **File Conversion**: Pandoc CLI
- **Requires**: Pandoc (install via `brew install pandoc`)

---

## Print Settings

Each job can specify:

- **Color Type**: `"bw"` (black & white) or `"color"` (RGB)
- **Copies**: Number of copies (1-99)
- **Page Range**: Start and end page for printing
- **Paper Size**: A4 (configurable via CUPS)
- **Resolution**: 600x600 DPI (configurable)

---

## Network Security

The agent only needs:

- **Outbound HTTPS** to `SUPABASE_URL` (443)
- **Local printer** access (USB or network)
- **No inbound** connections required

Recommended firewall rules:

```bash
# Allow outbound HTTPS only
ufw allow out 443

# Block everything else inbound
ufw default deny incoming
ufw default allow outgoing
```

---

## Troubleshooting

### Agent won't start

**Error**: `ModuleNotFoundError: No module named 'supabase'`

```bash
pip install -r requirements-rpi.txt
# Or:
pip install requests python-dotenv supabase Pillow
```

**Error**: `Missing required ENV variables`

```bash
# Check .env file exists and has all required variables
cat .env
# Should contain: SUPABASE_URL, SUPABASE_SERVICE_ROLE, PRINTER_ID, PRINTER_NAME
```

### Printer not detected

```bash
# List all USB devices
lsusb | grep -i canon
# Or for any printer:
lsusb

# List CUPS devices
lpinfo -v

# Restart CUPS
sudo systemctl restart cups

# Check CUPS status
sudo systemctl status cups
```

### Jobs not printing

1. **Check agent is running**: `sudo systemctl status vprint-agent`
2. **Check logs**: `sudo journalctl -u vprint-agent -n 50`
3. **Verify printer**: `lpstat -p -d`
4. **Test print**: `echo "test" | lp -d canon-printer-1`
5. **Check payment**: Ensure job `payment_status = 'paid'` in database

### File conversion fails

**Pandoc not found**:

```bash
# Install Pandoc
sudo apt install pandoc

# Verify
pandoc --version
```

**Pillow import error** (Images):

```bash
pip install Pillow
python3 -c "from PIL import Image; print('✓ Pillow OK')"
```

### Memory usage too high

On Raspberry Pi 3B+ (1GB RAM):

```bash
# Monitor memory
free -h

# Increase polling interval (slower job pickup, less CPU)
# Edit .env: POLL_INTERVAL=10

# Clear old logs
sudo journalctl --vacuum=size=10M
```

---

## Running as a Service

### Raspberry Pi (systemd) - Recommended

```bash
# Copy service file
sudo cp vprint-agent.service /etc/systemd/system/

# Enable on boot
sudo systemctl enable vprint-agent

# Start now
sudo systemctl start vprint-agent

# Check status
sudo systemctl status vprint-agent

# View live logs
sudo journalctl -u vprint-agent -f
```

### Windows (Task Scheduler)

1. Open `taskschd.msc`
2. Create Basic Task → "VPrint Agent"
3. Trigger: "When the computer starts"
4. Action: Start a program
5. Program: `python.exe`
6. Arguments: `agent.py`
7. Start in: Path to printer-agent folder

### Linux (systemd)

Copy the provided [vprint-agent.service](vprint-agent.service) file:

```bash
sudo cp vprint-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent
```

---

## Monitoring & Maintenance

### Check Status

```bash
# On Raspberry Pi
sudo journalctl -u vprint-agent -f

# Last 50 lines
sudo journalctl -u vprint-agent -n 50

# From specific time
sudo journalctl -u vprint-agent --since "10 minutes ago"
```

### Printer Queue

```bash
# List jobs in queue
lpq -P canon-printer-1

# Clear stuck jobs
sudo cancel -a

# Check printer capabilities
lpoptions -p canon-printer-1 -l
```

### System Resources

```bash
# Memory usage
free -h

# Disk usage
df -h

# Raspberry Pi temperature
vcgencmd measure_temp

# CPU usage
top -b -n 1 | head -10
```

---

## File Structure

```
printer-agent/
├── agent-rpi.py              # Cross-platform agent (recommended)
├── agent.py                  # Windows-only agent (legacy)
├── requirements.txt           # Windows dependencies
├── requirements-rpi.txt       # Raspberry Pi dependencies
├── .env.example              # Configuration template
├── vprint-agent.service      # Systemd service file
├── setup-rpi.sh              # Automated Raspberry Pi setup
├── README.md                 # This file
├── README-RPI.md             # Detailed Raspberry Pi guide
└── QUICKREF.md              # Quick reference commands
```

---

## Quick Reference

| Task               | Command                                                       |
| ------------------ | ------------------------------------------------------------- | ---------------------- |
| Run agent manually | `python3 agent-rpi.py`                                        |
| Test connection    | `python3 -c "from supabase import create_client; print('✓')"` |
| List printers      | `lpstat -p -d`                                                |
| Test print         | `echo "test"                                                  | lp -d canon-printer-1` |
| Start service      | `sudo systemctl start vprint-agent`                           |
| View logs          | `sudo journalctl -u vprint-agent -f`                          |
| Check memory       | `free -h`                                                     |
| Edit config        | `sudo nano ~/.env`                                            |

For more commands, see [QUICKREF.md](QUICKREF.md)

Then:

```bash
sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent
```
#   P r i n t e r - A g e n t  
 