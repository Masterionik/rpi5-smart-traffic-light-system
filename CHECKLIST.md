# 📋 Pre-Deployment Checklist

Use this checklist before running your Smart Traffic Light System for the first time or before demonstrations.

## ✅ Hardware Setup

### Raspberry Pi 5
- [ ] Pi 5 powered on and accessible
- [ ] Camera Module 3 connected and detected (`libcamera-hello` works)
- [ ] LED strip connected to GPIO 18
- [ ] LED strip powered by external 5V supply (NOT from Pi)
- [ ] Network connection working
- [ ] SSH access configured (if needed)

### Raspberry Pi 4 (Optional)
- [ ] Pi 4 powered on
- [ ] Touchscreen display connected and working
- [ ] Network connection to same WiFi as Pi 5
- [ ] Can ping Pi 5 from Pi 4

### LED Strip Wiring
- [ ] VCC (Red) → 5V External Power Supply
- [ ] GND (Black) → GND (shared with Pi GND)
- [ ] DATA (Green) → GPIO 18 (Pin 12)
- [ ] Double-check: NO direct 5V connection to Pi's 5V pin!

## ✅ Software Installation

### System Packages
- [ ] Python 3.10+ installed (`python3 --version`)
- [ ] pip updated (`pip install --upgrade pip`)
- [ ] System packages installed:
  ```bash
  sudo apt-get install libcamera-tools python3-libcamera python3-picamera2 python3-opencv
  ```

### Python Dependencies
- [ ] All packages from requirements.txt installed
  ```bash
  pip install -r requirements.txt
  ```
- [ ] No import errors when running `python3 test_system.py`

### YOLOv8 Model
- [ ] yolov8n.pt downloaded (will download automatically on first run)
- [ ] Or manually: `wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt`

## ✅ Configuration

### Django Settings (`myproject/settings.py`)
- [ ] `ALLOWED_HOSTS` includes your Pi's IP address
- [ ] `DEBUG = True` for development (set to `False` for production)
- [ ] `SECRET_KEY` is set (change for production)

### GPIO Permissions
- [ ] User added to gpio group:
  ```bash
  sudo usermod -a -G gpio $USER
  ```
- [ ] Or plan to run with sudo: `sudo python3 manage.py runserver`

### File Permissions
- [ ] All files readable
- [ ] Scripts executable:
  ```bash
  chmod +x start.sh test_system.py
  ```

## ✅ Testing

### Run System Tests
```bash
python3 test_system.py
```
- [ ] All imports pass
- [ ] Project structure correct
- [ ] LED controller initializes (or gracefully skips if no hardware)
- [ ] YOLO detector initializes
- [ ] Traffic controller initializes
- [ ] Pedestrian detector initializes

### Hardware Tests
- [ ] Camera preview works: `libcamera-hello`
- [ ] LED test (from Python console):
  ```python
  from hardware.led_strip import LEDStripController
  led = LEDStripController(num_pixels=8)
  led.set_all_green()
  # Should see all 8 LEDs turn green
  led.set_all_red()
  # Should see all 8 LEDs turn red
  ```

### Network Test
- [ ] Can access Pi from another device on network
- [ ] Firewall not blocking port 8000
- [ ] Test: `curl http://<pi-ip>:8000`

## ✅ First Run

### Start Server
```bash
# Option 1: Normal
python3 manage.py runserver 0.0.0.0:8000

# Option 2: With sudo (for GPIO)
sudo python3 manage.py runserver 0.0.0.0:8000

# Option 3: Use startup script
./start.sh
```

### Access Dashboard
- [ ] Open browser: `http://<pi-ip>:8000/camera/`
- [ ] Dashboard loads without errors
- [ ] Status shows "Raspberry Pi: Online"

### Enable Detection
- [ ] Click "Enable Detection" button
- [ ] Wait 10-30 seconds for YOLO model to load
- [ ] Detection status changes to "Enabled"
- [ ] FPS shows ~15-20

### Test Video Feed
- [ ] Main camera feed displays
- [ ] Video is smooth (not frozen)
- [ ] Can see detection boxes when objects in view

### Test LED Control
- [ ] Traffic lights in dashboard update
- [ ] Physical LEDs match dashboard colors
- [ ] Transitions are smooth
- [ ] All 4 directions work independently

### Test Mode Switching
- [ ] Click "Switch to MANUAL"
- [ ] Mode indicator changes to "MANUAL"
- [ ] Automatic cycling stops
- [ ] Click "Switch to AUTO" to return

### Test Emergency Stop
- [ ] Click "🚨 EMERGENCY STOP"
- [ ] All lights turn red immediately
- [ ] System switches to MANUAL mode

## ✅ Advanced Features (Optional)

### DroidCam Setup
- [ ] DroidCam app installed on Android phone
- [ ] Phone on same WiFi as Pi
- [ ] DroidCam URL entered in dashboard
- [ ] DroidCam feed connects successfully
- [ ] Pedestrian gesture detection overlay visible

### Test Pedestrian Gesture
- [ ] Point phone camera at traffic light
- [ ] Hold steady for 2 seconds
- [ ] Progress bar fills on screen
- [ ] Crossing request triggered
- [ ] Corresponding direction turns green

### Test Statistics
- [ ] Line chart updates with vehicle counts
- [ ] Per-direction counters increase when vehicles detected
- [ ] FPS counter shows reasonable values
- [ ] Event log shows system events

## ✅ Performance Check

### System Resources
```bash
# Check CPU usage
top
# Should be <80% with detection enabled

# Check memory
free -h
# Should have at least 500MB free

# Check temperature
vcgencmd measure_temp
# Should be <70°C under load
```

### Detection Performance
- [ ] FPS: 15-20 (with YOLO enabled)
- [ ] CPU: <80%
- [ ] No frame drops or freezing
- [ ] Detection boxes appear promptly

### Response Times
- [ ] Dashboard updates every ~2 seconds
- [ ] LED changes reflect within 50ms
- [ ] Button clicks respond immediately
- [ ] API calls return within 200ms

## ✅ Documentation Review

- [ ] Read QUICK_START.md
- [ ] Skim IMPLEMENTATION_GUIDE.md
- [ ] Understand LED configuration (8 LEDs = 4 directions)
- [ ] Know how to access event log
- [ ] Know emergency stop procedure

## ✅ Demonstration Prep

### Setup
- [ ] System running and stable
- [ ] Dashboard accessible
- [ ] Detection enabled
- [ ] Test objects (toy cars) ready
- [ ] Smartphone with DroidCam ready (if using)

### Talking Points
- [ ] Explain 8 LED configuration (2 per direction)
- [ ] Show real-time vehicle detection and counting
- [ ] Demonstrate dynamic green time allocation
- [ ] Show pedestrian gesture detection
- [ ] Explain anti-starvation algorithm
- [ ] Display statistics and event log

### Backup Plan
- [ ] Screenshots of working system
- [ ] Video recording of system in action
- [ ] Manual mode as fallback if AUTO has issues

## ✅ Troubleshooting Ready

### Know How To:
- [ ] Check logs: Console output or `tail -f /var/log/django.log`
- [ ] Restart system: Ctrl+C and restart server
- [ ] Reset to defaults: Emergency stop button
- [ ] Access without camera: Detection can be disabled
- [ ] Run without LEDs: System degrades gracefully

### Common Issues:
- [ ] LEDs not working → Run with sudo
- [ ] Camera not found → Check cable connection
- [ ] High CPU → Normal with YOLO enabled
- [ ] Slow YOLO loading → First load takes 10-30 sec
- [ ] DroidCam won't connect → Check WiFi and URL

## ✅ Safety

- [ ] Emergency stop tested and working
- [ ] System can be shut down cleanly (Ctrl+C)
- [ ] No loose wiring that could short
- [ ] External power supply for LEDs secured
- [ ] Cool-down plan if Pi overheats

## ✅ Final Verification

Run through this complete flow:
1. [ ] Start system with `./start.sh` or manual command
2. [ ] Open dashboard in browser
3. [ ] Enable detection
4. [ ] Wait for YOLO to load
5. [ ] Place toy car in view
6. [ ] Verify detection box appears
7. [ ] Check vehicle counter increases
8. [ ] Watch traffic lights cycle through colors
9. [ ] Verify physical LEDs match dashboard
10. [ ] Test emergency stop
11. [ ] Return to AUTO mode
12. [ ] (Optional) Test pedestrian gesture with DroidCam

---

## 🎯 Ready to Go!

If all items are checked:
- ✅ Hardware connected correctly
- ✅ Software installed and configured
- ✅ Tests passing
- ✅ System running smoothly
- ✅ Demo prepared

**You're ready to demonstrate your Smart Traffic Light System!** 🚦✨

---

## 📞 Quick Reference

### Start System
```bash
./start.sh
# or
python3 manage.py runserver 0.0.0.0:8000
```

### Access Dashboard
```
http://<pi-ip>:8000/camera/
```

### Run Tests
```bash
python3 test_system.py
```

### Emergency Shutdown
Press `Ctrl+C` in terminal, or use dashboard Emergency Stop button

---

**Good luck with your demonstration!** 🎉
