# 🚦 Smart Traffic Light System - Documentation

## Overview

This is a **Smart Traffic Light System** built with:
- **Raspberry Pi 5** as the main controller
- **Camera Module 3** for vehicle detection
- **YOLOv8** AI model for real-time object detection
- **WS2812 LED Strip** (8 LEDs) as a traffic light semaphore
- **Django Web Interface** for monitoring and control

---

## 📁 Project Structure

```
tf_si/
├── camera/                 # Django app for camera & web interface
│   ├── views.py           # API endpoints and video streaming
│   ├── urls.py            # URL routing
│   ├── droidcam.py        # Secondary camera support
│   └── templates/camera/  # HTML templates
│       ├── base.html      # Base template with navigation
│       ├── dashboard.html # Main dashboard
│       ├── analytics.html # Statistics and graphs
│       ├── cameras.html   # Camera management
│       └── settings.html  # System settings
│
├── detector/              # Detection and traffic control
│   ├── yolo_detector.py   # YOLOv8 car detection
│   ├── traffic_controller.py  # Traffic light logic
│   └── pedestrian_detector.py # Gesture detection
│
├── detection/             # Django app for database models
│   ├── models.py          # DetectionEvent, TrafficLightState, etc.
│   └── admin.py           # Django admin configuration
│
├── hardware/              # Hardware control
│   └── led_strip.py       # WS2812 LED controller (GPIO10/SPI)
│
├── myproject/             # Django project settings
│   ├── settings.py        # Django configuration
│   └── urls.py            # Root URL routing
│
├── manage.py              # Django management script
├── requirements.txt       # Python dependencies
└── test_led_strip.py      # LED test script
```

---

## 🔧 Module Descriptions

### 1. **hardware/led_strip.py** - LED Controller

Controls the WS2812 LED strip with **individual pixel control**.

**LED Layout (8 LEDs as traffic light):**
```
LED 0 ─┐
LED 1 ─┼─ 🔴 RED Section (3 LEDs)
LED 2 ─┘
LED 3 ─┬─ 🟡 YELLOW Section (2 LEDs)
LED 4 ─┘
LED 5 ─┐
LED 6 ─┼─ 🟢 GREEN Section (3 LEDs)
LED 7 ─┘
```

**States:**
- `RED` - Only LEDs 0,1,2 light up red
- `YELLOW` - Only LEDs 3,4 light up yellow
- `GREEN` - Only LEDs 5,6,7 light up green
- `RED_YELLOW` - Red + Yellow (transition state)
- `ALL_ON` - All sections lit (test mode)
- `OFF` - All LEDs off

**Technical Details:**
- Uses `adafruit-circuitpython-neopixel` library
- Connected to **GPIO10** (SPI MOSI) on Raspberry Pi 5
- Requires `sudo` for GPIO access

---

### 2. **detector/yolo_detector.py** - Vehicle Detection

Uses YOLOv8 AI model to detect vehicles in camera frames.

**How it works:**
1. Receives video frame from camera
2. Runs YOLOv8 inference (nano model for speed)
3. Detects objects: cars, trucks, buses, motorcycles
4. Returns count and bounding boxes

**Detected Classes:**
- `car` (class 2)
- `motorcycle` (class 3)
- `bus` (class 5)
- `truck` (class 7)

---

### 3. **detector/traffic_controller.py** - Traffic Logic

Controls the traffic light based on vehicle detection.

**Modes:**

| Mode | Description |
|------|-------------|
| **SIMPLE** | Immediate response - GREEN when car detected, RED when no car |
| **AUTO** | Intelligent cycling with timing algorithms |
| **MANUAL** | Control through web interface |

---

## 🚗 Traffic Light Logic (SIMPLE Mode)

The system uses **SIMPLE mode** by default for immediate response:

### State Machine:

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
    ┌───────────────────────────────┐                    │
    │           🔴 RED              │                    │
    │    (No vehicles detected)     │                    │
    └───────────────────────────────┘                    │
                    │                                     │
                    │ Vehicle detected                    │
                    ▼                                     │
    ┌───────────────────────────────┐                    │
    │       🔴🟡 RED + YELLOW       │                    │
    │    (1 second transition)      │                    │
    └───────────────────────────────┘                    │
                    │                                     │
                    │ After 1 second                      │
                    ▼                                     │
    ┌───────────────────────────────┐                    │
    │          🟢 GREEN             │◄─────────────┐     │
    │    (Vehicles can pass)        │              │     │
    └───────────────────────────────┘              │     │
                    │                              │     │
                    │ No vehicles for 5 seconds    │     │
                    ▼                              │     │
    ┌───────────────────────────────┐              │     │
    │         🟡 YELLOW             │   Vehicle    │     │
    │    (2 second warning)         │───detected───┘     │
    └───────────────────────────────┘                    │
                    │                                     │
                    │ After 2 seconds                     │
                    └─────────────────────────────────────┘
```

### Logic Explanation:

1. **Initial State: RED** 🔴
   - System starts with RED light
   - LEDs 0, 1, 2 are lit red
   - Waiting for vehicles

2. **Vehicle Detected → GREEN** 🟢
   - Camera detects a car/truck/bus/motorcycle
   - Brief RED+YELLOW transition (1 second)
   - Then GREEN light (LEDs 5, 6, 7 lit green)
   - **Vehicles can pass!**

3. **Vehicle Leaves → Back to RED** 🔴
   - No vehicle detected for 5 seconds
   - YELLOW warning (2 seconds)
   - Then RED light
   - **Vehicles must stop!**

4. **Vehicle Appears During Yellow → Stay GREEN**
   - If a vehicle is detected during yellow transition
   - Cancel transition, go back to GREEN immediately

### Timing Constants:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SIMPLE_GREEN_DURATION` | 5 sec | Time to wait before switching to RED |
| `SIMPLE_YELLOW_DURATION` | 2 sec | Yellow warning time |
| Red→Yellow→Green transition | 1 sec | Transition time |

---

## 🚶 Pedestrian Crossing

**Current Implementation:**
- Pedestrian can request crossing via web interface
- 30-second cooldown between requests
- Pedestrian crossing overrides vehicle detection

**Note:** In SIMPLE mode, the traffic light prioritizes vehicles:
- **GREEN** = Vehicles can pass (pedestrians should wait)
- **RED** = Vehicles stopped (pedestrians can cross)

---

## 📊 Database Models

### DetectionEvent
Logs every detection event:
- Event type (CAR, PEDESTRIAN, LED_CHANGE)
- Direction
- Vehicle count
- Timestamp

### TrafficLightState
Logs LED state changes:
- Current state (RED, YELLOW, GREEN)
- What triggered the change (DETECTION, MANUAL, AUTO)

### VehicleCount
Historical vehicle counts per direction.

### SystemStats
System performance statistics.

---

## 🌐 Web Interface

### Pages:

1. **Dashboard** (`/camera/`)
   - Live camera feed with detection overlay
   - Current traffic light status
   - Vehicle count
   - Mode selector (SIMPLE/AUTO/MANUAL)

2. **Analytics** (`/camera/analytics/`)
   - Detection statistics
   - Charts and graphs
   - Historical data

3. **Cameras** (`/camera/cameras/`)
   - Primary camera status
   - DroidCam secondary camera setup

4. **Settings** (`/camera/settings/`)
   - Traffic timing configuration
   - LED strip testing
   - Camera settings
   - Detection sensitivity

### API Endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/camera/status/` | GET | Camera status |
| `/camera/traffic/status/` | GET | Traffic light status |
| `/camera/traffic/mode/` | POST | Set mode (SIMPLE/AUTO/MANUAL) |
| `/camera/detection/toggle/` | POST | Enable/disable detection |
| `/camera/led/test/` | POST | Test LED strip |
| `/camera/pedestrian/request/` | POST | Request crossing |

---

## 🔌 Hardware Setup

### Connections:

| Component | RPi 5 Pin | Notes |
|-----------|-----------|-------|
| WS2812 LED Data | GPIO10 (Pin 19) | SPI MOSI |
| WS2812 LED GND | GND (Pin 6) | Common ground |
| WS2812 LED 5V | 5V (Pin 2) | External power recommended for >8 LEDs |
| Camera | CSI Port | Camera Module 3 |

### GPIO10 (SPI) for Raspberry Pi 5:
The neopixel library uses SPI on Pi 5, which is GPIO10 (MOSI), not GPIO18.

---

## 🚀 Running the System

```bash
# 1. Navigate to project
cd ~/Desktop/tf_smart_pi_v3/tf_si

# 2. Activate virtual environment
source venv/bin/activate

# 3. Run with sudo (required for GPIO access)
sudo venv/bin/python manage.py runserver 0.0.0.0:8000

# 4. Open in browser
# http://<raspberry-pi-ip>:8000/camera/
```

### Test LED Strip:
```bash
sudo venv/bin/python test_led_strip.py
```

---

## ❓ FAQ

### Q: Why does GREEN mean vehicles can pass?
**A:** This system is designed for **vehicle priority**:
- When a car is detected, the light turns GREEN to let it pass
- When no car is detected, the light turns RED (safe for pedestrians)

### Q: Can I change the timing?
**A:** Yes! Edit `detector/traffic_controller.py`:
```python
SIMPLE_GREEN_DURATION = 5  # Seconds before going to RED
SIMPLE_YELLOW_DURATION = 2  # Yellow warning time
```

### Q: How do I change the LED segment sizes?
**A:** Edit `hardware/led_strip.py`:
```python
RED_LEDS = [0, 1, 2]      # First 3 LEDs
YELLOW_LEDS = [3, 4]       # Middle 2 LEDs
GREEN_LEDS = [5, 6, 7]     # Last 3 LEDs
```

### Q: Why use GPIO10 instead of GPIO18?
**A:** Raspberry Pi 5 uses SPI for NeoPixel LEDs. GPIO10 is the SPI MOSI pin, which is required for the `adafruit-circuitpython-neopixel` library on Pi 5.

---

## 📝 Summary

| Component | Technology | Purpose |
|-----------|------------|---------|
| Brain | Raspberry Pi 5 | Main controller |
| Eyes | Camera Module 3 + YOLOv8 | Vehicle detection |
| Light | WS2812 LED Strip | Traffic semaphore |
| Interface | Django + HTML/CSS/JS | Web control |
| Database | SQLite | Event logging |

**Traffic Logic:** 
- 🚗 Car detected → 🟢 GREEN (let it pass)
- 🚗 Car leaves → 🟡 YELLOW (warning)
- No cars → 🔴 RED (safe for pedestrians)
