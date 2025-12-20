# Raspberry Pi Camera Dashboard - Complete Setup Guide

## Quick Setup on Raspberry Pi 5

### 1. System Dependencies
```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv libatlas-base-dev libjasper-dev
sudo apt-get install -y libcamera-tools python3-libcamera python3-picamera2
```

### 2. Clone Project
```bash
cd ~
git clone https://github.com/igorluchita/labv2.git
cd labv2
```

### 3. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Fix libcamera Access
This is critical - libcamera is a system package that must be accessible from the venv:

```bash
# Create a .pth file to include system packages
echo "/usr/lib/python3/dist-packages" >> venv/lib/python3.13/site-packages/system-packages.pth

# Verify it works
python3 -c "from libcamera import controls; print('✓ libcamera OK')"
```

### 5. Install Python Packages
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Run Migrations
```bash
python manage.py migrate
```

### 7. Start Server
```bash
python manage.py runserver 0.0.0.0:8000
```

Then open browser to: `http://<your-pi-ip>:8000`

## Troubleshooting

### libcamera "No module named 'libcamera'"

**Solution 1: Create .pth file manually**
```bash
# While venv is activated
python3 << 'EOF'
import site
import os

site_packages = site.getsitepackages()[0]
pth_file = os.path.join(site_packages, 'system-packages.pth')

with open(pth_file, 'w') as f:
    f.write('/usr/lib/python3/dist-packages\n')

print(f"Created {pth_file}")

# Verify
import libcamera
print(f"✓ libcamera OK: {libcamera.__file__}")
EOF
```

**Solution 2: Use system Python (not recommended)**
If venv approach fails, use system Python:
```bash
sudo python3 -m pip install -r requirements.txt
sudo python3 manage.py migrate
sudo python3 manage.py runserver 0.0.0.0:8000
```

### Permissions Issues
```bash
# Run with proper permissions for camera access
sudo usermod -a -G video $USER
# Log out and back in for group changes to take effect
```

### YOLO Model Download Issues
The first time you enable detection, YOLO will download the model (~30MB):
```bash
# Pre-download to avoid download during runtime
python3 << 'EOF'
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
EOF
```

## Performance Tips

1. **Use smaller YOLO model**: Already using `yolov8n.pt` (nano)
2. **Adjust detection settings** in `detector/yolo_detector.py`:
   - Change `conf=0.5` to higher value (0.6-0.7) to reduce false positives
   - Reduce resolution if CPU is maxed out
3. **Monitor resources**:
   ```bash
   top
   free -h
   vcgencmd measure_temp  # Check temperature
   ```

## Production Deployment with Gunicorn

```bash
pip install gunicorn

# Run with 2 workers (RPi5 has 4 cores)
gunicorn --workers=2 --threads=2 --worker-class=gthread \
         --bind 0.0.0.0:8000 --timeout 120 myproject.wsgi:application
```

## Systemd Service (Optional)

Create `/etc/systemd/system/camera-dashboard.service`:

```ini
[Unit]
Description=Raspberry Pi Camera Dashboard
After=network.target

[Service]
Type=notify
User=pi
WorkingDirectory=/home/pi/labv2
Environment="PATH=/home/pi/labv2/venv/bin"
ExecStart=/home/pi/labv2/venv/bin/gunicorn --workers=2 --bind 0.0.0.0:8000 myproject.wsgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable camera-dashboard
sudo systemctl start camera-dashboard
sudo systemctl status camera-dashboard
sudo journalctl -u camera-dashboard -f  # View logs
```

## API Endpoints

- `GET /` - Dashboard
- `GET /camera/feed/` - Video stream (MJPEG)
- `GET /camera/status/` - Camera & detection status
- `POST /camera/detection/toggle/` - Toggle car detection
- `GET /camera/detection/stats/` - Detection statistics
- `POST /camera/shutdown/` - Shutdown camera

## Features

- ✅ Live video streaming from Camera Module 3
- ✅ YOLO car detection with real-time bounding boxes
- ✅ Car counting
- ✅ Web dashboard
- ✅ Optimized for Raspberry Pi 5
