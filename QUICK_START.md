# Quick Start Guide - Smart Traffic Light System

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- Raspberry Pi 5 with Camera Module 3 connected
- WS2812B LED strip (8 LEDs) connected to GPIO 10 (SPI)
- Python 3.10+
- All dependencies installed (see below)

### 1. Install Dependencies (First Time Only)
```bash
cd /path/to/tf_si
pip install -r requirements.txt
pip install rpi5-ws2812  # LED strip library for RPi 5
```

### 2. Setup Database (First Time Only)
```bash
python manage.py makemigrations detection
python manage.py migrate
```

### 3. Start the System
```bash
sudo python manage.py runserver 0.0.0.0:8000
```
> Note: `sudo` is required for LED strip control via SPI

### 4. Open Dashboard
Open browser and navigate to:
```
http://<your-pi-ip>:8000/camera/
```

### 5. Enable Vehicle Detection
1. Click "Enable Detection" button in dashboard
2. Wait 5-10 seconds for YOLO model to load
3. Vehicle detection will start automatically

---

## 🎮 Quick Feature Guide

### LED Strip Configuration (8 LEDs as Traffic Light)
Your 8 LED strip is configured as a single traffic light:
- **LEDs 0-2 (First 3)**: RED section
- **LEDs 3-4 (Middle 2)**: YELLOW section
- **LEDs 5-7 (Last 3)**: GREEN section

This mimics a real traffic light where only one section lights up at a time.

### Control Modes

#### SIMPLE Mode (Default - Recommended)
- **Vehicle Detected** → GREEN section lights up (go)
- **No Vehicle** → RED section lights up (stop)
- Transitions through YELLOW for safety
- Instant response to detection!

#### AUTO Mode
- Traditional cycling traffic light
- Dynamic timing based on vehicle counts
- Good for multiple camera setups

#### MANUAL Mode
- Direct control through the UI
- Useful for testing and debugging

### How Detection Works
1. Camera captures video stream
2. YOLO detects vehicles in 4 ROI quadrants (NORTH, EAST, SOUTH, WEST)
3. When any vehicle is detected:
   - LED strip shows GREEN (go)
4. When no vehicles detected:
   - After timeout, LED shows YELLOW then RED

### Database Logging
All detection events are stored in Django database:
- Vehicle detections with timestamps
- LED state changes
- System events

View them in the Analytics page or Django Admin.

### Vehicle Detection
- Automatically counts vehicles in each direction
- Shows bounding boxes around detected vehicles
- Displays per-direction counts
- Updates traffic light timing based on density

### Pedestrian Crossing (Smartphone Gesture)
1. Install DroidCam app on Android phone
2. Start DroidCam (note the IP address shown)
3. In dashboard: Enter DroidCam URL (e.g., `http://192.168.1.100:4747/mjpegfeed`)
4. Click "Connect DroidCam"
5. Point phone camera at traffic light and hold steady for 2 seconds
6. System detects gesture and triggers pedestrian crossing!

---

## 🔧 Troubleshooting

### LEDs Not Working?
```bash
# Run with sudo (required for GPIO access)
sudo python manage.py runserver 0.0.0.0:8000
```

### Camera Not Found?
```bash
# Test camera
libcamera-hello

# If error, check connection:
# 1. Power off Pi
# 2. Reconnect camera cable
# 3. Power on and try again
```

### YOLO Model Slow?
This is normal on Raspberry Pi 5. Expected FPS:
- Without detection: 25-30 FPS
- With YOLO detection: 15-20 FPS

### DroidCam Won't Connect?
Make sure:
1. Phone and Pi on same WiFi network
2. DroidCam app is running on phone
3. URL format: `http://<phone-ip>:4747/mjpegfeed`

---

## 📊 Dashboard Overview

### Top Status Bar
- **Mode**: AUTO or MANUAL
- **Active Direction**: Currently green direction
- **Total Vehicles**: Count across all directions
- **FPS**: Processing speed

### Video Feeds
- **Left**: Main camera (Camera Module 3)
- **Right**: DroidCam (smartphone camera)

### Traffic Lights
Each direction shows:
- Visual light indicators (red/yellow/green)
- Vehicle count
- Pedestrian crossing button

### Statistics Chart
Real-time line chart showing vehicle counts per direction over time.

### Event Log
Bottom panel shows recent system events:
- Traffic light changes
- Pedestrian requests
- Mode changes
- Emergency stops

---

## 🎯 Common Tasks

### Test LED Strip
```python
# In Python console
from hardware.led_strip import LEDStripController
led = LEDStripController(num_pixels=8)

# Test each direction
led.set_direction_state(0, 'GREEN')  # North green
led.set_direction_state(1, 'RED')    # East red
led.set_all_red()  # All red
```

### Check System Status
Visit: `http://<pi-ip>:8000/camera/traffic/status/`

Returns JSON with complete system state.

### Emergency Stop
Click red "🚨 EMERGENCY STOP" button in dashboard.
- Sets all lights to RED immediately
- Switches to MANUAL mode
- Stops automatic cycling

### View Logs
```bash
# Django logs
tail -f /var/log/django.log

# Or check console output where server is running
```

---

## 📱 Mobile Access

The dashboard is mobile-friendly! Access from:
- Tablet
- Phone browser
- Another computer on same network

URL: `http://<pi-ip>:8000/camera/`

---

## 🔐 Security Notes

For production use:
1. Change Django `SECRET_KEY` in `myproject/settings.py`
2. Set `DEBUG = False`
3. Configure proper `ALLOWED_HOSTS`
4. Use HTTPS with SSL certificate
5. Add authentication to dashboard

---

## 📈 Monitoring Tips

### Check Performance
- FPS should be 15-20 with detection enabled
- CPU usage should be <80%
- Dashboard updates every 2 seconds

### Verify LED Sync
- Watch LEDs while viewing dashboard
- Colors should match exactly
- No visible lag (<50ms)

### Test Detection Accuracy
1. Place toy cars in camera view
2. Check if detection boxes appear
3. Verify counts are accurate
4. Move cars to different directions and verify ROI detection

---

## 🎓 Next Steps

Once system is running:
1. Adjust ROI zones for your camera angle (in code)
2. Tune detection confidence threshold
3. Calibrate green light timing (T_MIN, T_MAX)
4. Add more directions if needed
5. Implement data logging for analytics

---

## 💡 Pro Tips

1. **Better Performance**: Lower camera resolution to 640×480
2. **Smoother Transitions**: Increase T_YELLOW duration
3. **More Responsive**: Reduce polling interval in dashboard
4. **Better Accuracy**: Improve lighting conditions for camera
5. **Longer Battery**: Reduce LED brightness value

---

## 🆘 Getting Help

If stuck:
1. Check IMPLEMENTATION_GUIDE.md for detailed docs
2. Review event log in dashboard
3. Check console output for error messages
4. Verify hardware connections
5. Try restarting the system

---

## 📦 Project Structure

```
tf_si/
├── camera/                    # Main Django app
│   ├── views.py              # API endpoints
│   ├── urls.py               # URL routing
│   └── templates/camera/
│       └── dashboard.html    # Web interface
├── detector/
│   ├── yolo_detector.py      # Vehicle detection
│   ├── traffic_controller.py # Traffic algorithm
│   └── pedestrian_detector.py # Gesture detection
├── hardware/
│   └── led_strip.py          # LED control (8 LEDs)
└── manage.py                 # Django entry point
```

---

**System Ready!** 🚦✨

Open `http://<pi-ip>:8000/camera/` and enjoy your smart traffic light system!
