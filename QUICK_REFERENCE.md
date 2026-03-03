# VPrint Raspberry Pi - Quick Reference

## Essential SSH Commands

### Remote Access

```bash
# Connect to Raspberry Pi
ssh pi@vprint-rpi.local

# Copy files to Pi
scp filename.txt pi@vprint-rpi.local:/home/pi/

# Copy files from Pi
scp pi@vprint-rpi.local:/home/pi/filename.txt .
```

## Service Management

```bash
# Check if agent is running
sudo systemctl status vprint-agent

# Start the agent
sudo systemctl start vprint-agent

# Stop the agent
sudo systemctl stop vprint-agent

# Restart the agent
sudo systemctl restart vprint-agent

# View real-time logs (press Ctrl+C to exit)
sudo journalctl -u vprint-agent -f

# View last 50 lines of logs
journalctl -u vprint-agent -n 50

# View logs from last 10 minutes
journalctl -u vprint-agent --since "10 minutes ago"

# Disable auto-start (emergency)
sudo systemctl disable vprint-agent

# Enable auto-start
sudo systemctl enable vprint-agent
```

## Printer Commands

```bash
# List all printers
lpstat -p -d

# Print a test page
echo "Test Page" | lp

# Print to specific printer
echo "Test" | lp -d HP_LaserJet_Pro_M404n

# Check printer status
lpstat -p -l

# Print a PDF file
lp /path/to/file.pdf

# Print with specific copies
lp -n 3 /path/to/file.pdf

# Print page range
lp -P 1-5 /path/to/file.pdf

# Print and specify printer
lp -d PRINTER_NAME /path/to/file.pdf
```

## Configuration & Environment

```bash
# Edit environment variables
nano ~/print666/print/printer-agent/.env

# Check current configuration
cat ~/print666/print/printer-agent/.env

# Create backup of configuration
cp ~/.env ~/.env.backup

# Restart service after changing .env
sudo systemctl restart vprint-agent
```

## System Status

```bash
# Check WiFi connection
iwconfig

# Check IP address
hostname -I

# Check internet connection
ping 8.8.8.8

# Reboot Raspberry Pi
sudo reboot

# Shutdown Raspberry Pi
sudo shutdown -h now

# Check disk space
df -h

# Check memory usage
free -h

# Check CPU temperature
vcgencmd measure_temp
```

## Troubleshooting

```bash
# Agent won't start?
sudo systemctl status vprint-agent
journalctl -u vprint-agent -n 100

# Printer not detected?
lsusb
lpstat -p -d

# Supabase connection error?
python3 -c "from supabase import create_client; print('OK')"

# Check logs for specific job
journalctl -u vprint-agent -g "job_id_here"

# Full system diagnostics
sudo systemctl status vprint-agent
lpstat -p -d
echo "Disk:" && df -h
echo "Memory:" && free -h
echo "Network:" && hostname -I
```

## File Locations

```bash
# Main agent script
~/print666/print/printer-agent/agent_linux.py

# Configuration file
~/print666/print/printer-agent/.env

# Log files (systemd)
journalctl -u vprint-agent

# Local logs (if configured)
~/print666/print/printer-agent/logs/agent.log

# Systemd service file
/etc/systemd/system/vprint-agent.service
```

## Common Issues & Solutions

| Issue              | Command                               | Note                       |
| ------------------ | ------------------------------------- | -------------------------- |
| Agent not running  | `sudo systemctl restart vprint-agent` | Check logs after restart   |
| Printer not found  | `lpstat -p -d`                        | Plug in USB, wait 15s      |
| Connection timeout | `ping 8.8.8.8`                        | Check WiFi connection      |
| Permission denied  | `sudo usermod -a -G lpadmin pi`       | Add pi to printer group    |
| Agent crashes      | `journalctl -u vprint-agent -f`       | Watch logs in real-time    |
| .env not loaded    | `sudo systemctl restart vprint-agent` | Restart after editing .env |

## Useful URLs

```
Supabase Dashboard: https://app.supabase.com
Razorpay Dashboard: https://dashboard.razorpay.com
VPrint Frontend: https://your-deployed-url.com
Vercel Dashboard: https://vercel.com/dashboard
```

## Remote Support

If you need to debug remotely:

```bash
# Share recent logs with supportive via terminal
journalctl -u vprint-agent --since "1 hour ago" | tail -100

# Generate full diagnostic report
echo "=== System Info ===" && uname -a
echo "=== Pi Model ===" && cat /proc/device-tree/model
echo "=== Network ===" && hostname -I
echo "=== Printers ===" && lpstat -p -d
echo "=== Service ===" && sudo systemctl status vprint-agent
echo "=== Agent Version ===" && head -5 ~/print666/print/printer-agent/agent_linux.py
```
