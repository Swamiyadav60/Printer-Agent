# VPrint Printer Agent - Linux/Raspberry Pi Version

A Python-based printer agent that runs on Linux systems (Raspberry Pi Zero W, Ubuntu, Debian, etc.) to handle print jobs from the VPrint kiosk system.

## What This Agent Does

The VPrint Printer Agent:

1. **Polls Supabase** every 3 seconds for new print jobs assigned to this printer
2. **Downloads files** from Supabase storage using signed URLs
3. **Sends to printer** via CUPS (Common Unix Printing System)
4. **Updates job status** (processing → completed/failed)
5. **Runs 24/7** as a systemd background service

## System Requirements

### Hardware

- **Raspberry Pi Zero W** (with WiFi)
- **USB Printer** (any printer supported by CUPS)
- **Power supply** (5V, 2A)
- **SD Card** (16GB+)
- **Stable WiFi/Network connection**

### Operating System

- **Raspberry Pi OS Lite** (64-bit recommended)
- **Ubuntu Desktop/Server** 20.04 or later
- **Debian Bullseye or later**
- **Any Linux distribution** with CUPS support

### Software Dependencies

- Python 3.8+
- pip3 (Python package manager)
- CUPS (Common Unix Printing System)
- Git (optional, for cloning repository)

## Installation

### Quick Setup (Automated)

```bash
# Download and run setup script
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/print666/main/print/printer-agent/setup_raspberrypi.sh
chmod +x setup_raspberrypi.sh
./setup_raspberrypi.sh
```

### Manual Setup

#### 1. Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

#### 2. Install CUPS (Printer Service)

```bash
sudo apt-get install -y cups cups-client libcups2-dev
sudo systemctl start cups
sudo systemctl enable cups
sudo usermod -a -G lpadmin pi
```

#### 3. Install Python

```bash
sudo apt-get install -y python3 python3-pip git
```

#### 4. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/print666.git
cd print666/print/printer-agent
```

#### 5. Install Python Dependencies

```bash
pip3 install -r requirements-linux.txt
```

#### 6. Configure Environment

```bash
cp .env.example .env
nano .env
```

**Edit .env with your values:**

```env
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
PRINTER_ID=550e8400-e29b-41d4-a716-446655440000
PRINTER_NAME=HP_LaserJet_Pro_M404n
POLL_INTERVAL=3
```

#### 7. Test Agent

```bash
python3 agent_linux.py
```

Press Ctrl+C to stop.

#### 8. Install as Systemd Service

```bash
sudo cp vprint-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vprint-agent
sudo systemctl start vprint-agent
```

## Configuration

### Environment Variables (.env)

| Variable                | Required | Description                 | Example                                |
| ----------------------- | -------- | --------------------------- | -------------------------------------- |
| `SUPABASE_URL`          | Yes      | Supabase project URL        | `https://xyz.supabase.co`              |
| `SUPABASE_SERVICE_ROLE` | Yes      | Supabase service role key   | `eyJhbGciOi...`                        |
| `PRINTER_ID`            | Yes      | UUID of printer in database | `550e8400-e29b-41d4-a716-446655440000` |
| `PRINTER_NAME`          | No       | Exact CUPS printer name     | `HP_LaserJet_Pro_M404n`                |
| `POLL_INTERVAL`         | No       | Seconds between job polls   | `3` (default)                          |
| `BACKEND_API_URL`       | No       | Custom API endpoint         | `https://api.example.com/api/jobs`     |

### Get Your Supabase Credentials

1. Login to https://app.supabase.com
2. Select your project
3. Go to **Settings → API**
4. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **Service Role Secret** → `SUPABASE_SERVICE_ROLE`

### Find Your Printer Name

```bash
# List all connected printers
lpstat -p -d

# Detailed printer information
lpstat -p -l

# Example output:
# printer HP_LaserJet_Pro_M404n is idle. enabled since Mon 01 Jan 2025 10:00:00 AM UTC
```

## Usage

### Start Agent

```bash
python3 agent_linux.py
```

### As Systemd Service

```bash
# Start
sudo systemctl start vprint-agent

# Stop
sudo systemctl stop vprint-agent

# Restart
sudo systemctl restart vprint-agent

# Check status
sudo systemctl status vprint-agent

# View logs
sudo journalctl -u vprint-agent -f

# View past logs
journalctl -u vprint-agent -n 50
```

### Manual Printer Test

```bash
# List printers
lpstat -p -d

# Test print to specific printer
echo "Test Page" | lp -d HP_LaserJet_Pro_M404n

# Print PDF file
lp -d HP_LaserJet_Pro_M404n /path/to/file.pdf

# Print 3 copies
lp -n 3 -d HP_LaserJet_Pro_M404n /path/to/file.pdf

# Print page range
lp -P 1-5 -d HP_LaserJet_Pro_M404n /path/to/file.pdf
```

## Logging

### View Real-Time Logs

```bash
sudo journalctl -u vprint-agent -f
```

### View Log History

```bash
# Last 50 lines
journalctl -u vprint-agent -n 50

# Last 1 hour
journalctl -u vprint-agent --since "1 hour ago"

# Last 24 hours
journalctl -u vprint-agent --since "24 hours ago"

# All logs for today
journalctl -u vprint-agent --since today
```

### Local Log Files (if configured)

```bash
cat ~/print666/print/printer-agent/logs/agent.log
```

## Troubleshooting

### Agent Won't Start

```bash
# Check status
sudo systemctl status vprint-agent

# Check logs
journalctl -u vprint-agent -n 100

# Test manually
python3 agent_linux.py
```

**Solutions:**

- Missing .env file: `cp .env.example .env`
- Wrong credentials: Check SUPABASE_URL and SUPABASE_SERVICE_ROLE
- Missing dependencies: `pip3 install -r requirements-linux.txt`

### Printer Not Found

```bash
# List printers
lpstat -p -d

# If empty, check USB
lsusb

# Restart CUPS
sudo systemctl restart cups
```

### Connection Timeout to Supabase

```bash
# Check internet
ping 8.8.8.8

# Check DNS
nslookup supabase.co

# Verify .env
cat .env
```

### Jobs Not Processing

```bash
# Check if agent is running
sudo systemctl status vprint-agent

# Watch real-time logs
sudo journalctl -u vprint-agent -f

# Check Supabase for pending jobs
# Login to https://app.supabase.com
# Go to: Database → print_jobs
# Look for: status = 'pending' or status = 'queued'
```

## Performance Monitoring

```bash
# CPU temperature (Raspberry Pi only)
vcgencmd measure_temp

# Memory usage
free -h

# Disk usage
df -h

# Process info
ps aux | grep agent_linux

# Top processes
top -n1 | head -15
```

## Common Issues

| Issue                         | Cause                | Solution                                 |
| ----------------------------- | -------------------- | ---------------------------------------- |
| "lp command not found"        | CUPS not installed   | `sudo apt-get install cups`              |
| "Module not found: supabase"  | Dependencies missing | `pip3 install -r requirements-linux.txt` |
| "HTTP 405 Method Not Allowed" | API endpoint issue   | Check API configuration                  |
| "Printer name invalid"        | CUPS name wrong      | Run `lpstat -p -l`                       |
| "Connection refused"          | WiFi down            | Check `hostname -I`                      |
| "File download failed"        | Storage permissions  | Check Supabase storage RLS               |
| "Service won't start"         | .env path wrong      | Verify WorkingDirectory in service file  |

## Differences from Windows Version

| Feature           | Windows (agent.py) | Linux (agent_linux.py) |
| ----------------- | ------------------ | ---------------------- |
| Print driver      | SumatraPDF.exe     | CUPS (lp command)      |
| Printer detection | Native Windows     | lpstat command         |
| Service           | Windows Service    | systemd                |
| File paths        | Windows paths      | Linux paths            |
| Dependencies      | pywin32            | libcups2-dev           |
| Compatibility     | Windows only       | Linux/Raspberry Pi     |

## File Locations

```
/home/pi/print666/print/printer-agent/
├── agent_linux.py              # Main agent script
├── requirements-linux.txt      # Python dependencies
├── .env                        # Configuration (DO NOT COMMIT)
├── .env.example               # Configuration template
├── vprint-agent.service       # Systemd service file
├── setup_raspberrypi.sh       # Automated setup script
├── COMPLETE_SETUP_GUIDE.md    # Full setup guide
├── RASPBERRY_PI_SETUP_GUIDE.md # Detailed Pi guide
├── QUICK_REFERENCE.md         # Command reference
└── logs/
    └── agent.log              # Application logs

/etc/systemd/system/
└── vprint-agent.service       # Installed service file

/home/pi/print666/
├── print/
│   ├── src/                   # Frontend source code
│   ├── package.json
│   └── README.md
```

## Security Considerations

1. **Protect .env file**

   ```bash
   chmod 600 .env
   ```

2. **SUPABASE_SERVICE_ROLE is SECRET**
   - Never commit to public repositories
   - Never share via email or chat
   - Rotate if exposed

3. **Run as non-root user**
   - Service runs as `pi` user by default
   - CUPS configured for `pi` user

4. **Use HTTPS only**
   - All API calls use HTTPS
   - Supabase enforces HTTPS

5. **Backup credentials**
   ```bash
   cp .env ~/.env.backup.$(date +%Y%m%d)
   chmod 600 ~/.env.backup.*
   ```

## Maintenance

### Daily

```bash
sudo systemctl status vprint-agent
journalctl -u vprint-agent -n 20
```

### Weekly

```bash
sudo apt-get update
journalctl -u vprint-agent --since "1 week ago" | grep ERROR
```

### Monthly

```bash
sudo apt-get upgrade
sudo journalctl --vacuum=time=30d
df -h  # Check disk space
```

## Updating the Agent

```bash
# Stop service
sudo systemctl stop vprint-agent

# Pull latest code
cd ~/print666
git pull origin main

# Install new dependencies (if any)
pip3 install -r print/printer-agent/requirements-linux.txt

# Restart service
sudo systemctl start vprint-agent

# Verify
sudo systemctl status vprint-agent
```

## Support

For detailed setup guide: See `COMPLETE_SETUP_GUIDE.md`
For quick commands: See `QUICK_REFERENCE.md`
For Raspberry Pi specific: See `RASPBERRY_PI_SETUP_GUIDE.md`

## License

Part of VPrint Printing Kiosk System - Proprietary
