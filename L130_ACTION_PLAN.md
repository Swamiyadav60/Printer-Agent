# ✅ YOUR VPRINT SETUP - EPSON L130 ACTION PLAN

## Your Exact Configuration

```
Hardware:
- Raspberry Pi Zero W ✓
- Raspberry Pi OS 32-bit Lite ✓
- Epson L130 Printer ✓

Software:
- VPrint Kiosk system
- Supabase backend
- Razorpay payment
```

---

## 📋 SETUP CHECKLIST (Do These Steps)

### PHASE 1: On Your Laptop (30 minutes)

- [ ] Go to Supabase Dashboard
- [ ] Copy: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE` from Settings → API
- [ ] Register Epson L130 in `printers` table:
  ```sql
  INSERT INTO printers (name, location_id, model, status)
  VALUES ('Epson L130', 1, 'Epson EcoTank L130', 'active')
  RETURNING id;
  ```
- [ ] Copy the returned UUID → This is your `PRINTER_ID`
- [ ] Deploy frontend to Vercel (or self-host)
- [ ] Note your Frontend URL

**Save these 3 values:**

- SUPABASE_URL
- SUPABASE_SERVICE_ROLE
- PRINTER_ID

---

### PHASE 2: Raspberry Pi Hardware (15 minutes)

**You already have 32-bit Lite OS!**

- [ ] Use USB hub connected to Raspberry Pi
- [ ] Connect Epson L130 to USB hub
- [ ] Power on Raspberry Pi
- [ ] Power on Epson L130
- [ ] Connect to WiFi (already configured during imaging)
- [ ] Find Pi's IP: `ping vprint-rpi.local` from your laptop

---

### PHASE 3: Software Setup on Raspberry Pi (45 minutes)

**SSH into Pi:**

```bash
ssh pi@vprint-rpi.local
# Password: (your password)
```

**Follow These TWO Guides in Order:**

#### STEP 1: Read & Follow "SETUP_32BIT_LITE.md"

- This is your 32-bit OS setup guide
- Has 12 numbered steps
- All commands are copy-paste ready
- Works for any Epson printer

#### STEP 2: Reference "EPSON_L130_SETUP_GUIDE.md"

- This is L130-specific information
- Helps with printer detection
- Troubleshooting for L130
- USB ID: `04b8:0a37`

#### STEP 3: The ONE Difference for L130

When you create `.env` file in step 10 of SETUP_32BIT_LITE.md, use:

```env
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE=eyJhbGciOi...
PRINTER_ID=YOUR_UUID_HERE
PRINTER_NAME=Epson_L130_Series
POLL_INTERVAL=3
```

**Key line:** `PRINTER_NAME=Epson_L130_Series` (NOT L3210!)

---

### PHASE 4: Testing (10 minutes)

1. **Verify printer detected:**

   ```bash
   lpstat -p -d
   # Should show: printer Epson_L130_Series is idle...
   ```

2. **Test manual print to L130:**

   ```bash
   echo "Test" | lp -d Epson_L130_Series
   # Check if Epson L130 printed
   ```

3. **Verify agent running:**

   ```bash
   sudo systemctl status vprint-agent
   # Should show: active (running)
   ```

4. **Upload test job via frontend**
   - Open your frontend URL
   - Upload PDF file
   - Make test payment
   - Check if Epson L130 prints!

5. **Check agent logs:**
   ```bash
   sudo journalctl -u vprint-agent -f
   # Should show job processing
   ```

---

## 📖 EXACT FILES TO READ (IN ORDER)

1. **00_READ_ME_FIRST.md** (2 min) ← You're reading this!
2. **SETUP_32BIT_LITE.md** (15 min) ← Main setup guide
3. **EPSON_L130_SETUP_GUIDE.md** (15 min) ← Your printer guide
4. **QUICK_REFERENCE.md** (keep open) ← Commands reference

---

## ⚡ QUICK COMMAND SUMMARY

```bash
# Connect to Pi
ssh pi@vprint-rpi.local

# Check printer
lpstat -p -d

# Test print to L130
echo "Test" | lp -d Epson_L130_Series

# Check agent
sudo systemctl status vprint-agent

# Watch logs
sudo journalctl -u vprint-agent -f

# Printer info
lsusb | grep -i epson
```

---

## 🎯 SUCCESS INDICATORS

You'll know it's working when:

✓ `lpstat -p -d` shows `Epson_L130_Series`
✓ Manual print command works
✓ `sudo systemctl status vprint-agent` shows "active (running)"
✓ Agent logs show job processing
✓ Frontend shows "Print Completed"
✓ PDF appears at Epson L130 printer!

---

## 📂 FILE LOCATIONS

All files are in:

```
print666/print/printer-agent/
```

**Key files you'll use:**

- `SETUP_32BIT_LITE.md` - Main setup
- `EPSON_L130_SETUP_GUIDE.md` - Your printer
- `agent_linux.py` - The agent (already ready!)
- `.env.example` - Configuration template

---

## ⚠️ IMPORTANT REMINDERS

1. **Only one difference for L130:**
   - In `.env` file: `PRINTER_NAME=Epson_L130_Series`
   - Everything else is identical to other Epson printers

2. **Use 32-bit Lite commands:**
   - All commands in `SETUP_32BIT_LITE.md` are for 32-bit
   - Don't use 64-bit guides

3. **L130 is older/slower than L3210:**
   - Print speed: 27 ppm (vs 38 ppm for L3210)
   - But much cheaper: ₹0.30/page (vs ₹0.50 for L3210)

4. **Printer name format:**
   - Must be exactly: `Epson_L130_Series`
   - Check with: `lpstat -p -l`

---

## 🚀 NEXT ACTION RIGHT NOW

1. **Open:** `SETUP_32BIT_LITE.md`
2. **Read:** First 15 minutes
3. **Start:** With Step 1
4. **Copy-paste:** All commands

**That's it! You're ready to build!** 🎉

---

## 💡 YOU HAVE EVERYTHING READY

✓ 11 complete guides (200+ pages)
✓ Copy-paste commands
✓ L130-specific setup
✓ 32-bit Lite optimized
✓ Troubleshooting included
✓ Quick reference available

**There's nothing missing. Everything is prepared for your exact setup!**

---

## 📞 IF SOMETHING GOES WRONG

1. **Printer not detected?**
   → Read: EPSON_L130_SETUP_GUIDE.md → Troubleshooting

2. **Agent won't start?**
   → Read: SETUP_32BIT_LITE.md → Check .env file

3. **Need specific command?**
   → Open: QUICK_REFERENCE.md → Search (Ctrl+F)

4. **General issues?**
   → Read: COMPLETE_SETUP_GUIDE.md → Troubleshooting

---

**Your Epson L130 self-service kiosk is minutes away from working!**

**Go read SETUP_32BIT_LITE.md now!** 👉

Good luck! 🍓🖨️
