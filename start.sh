#!/bin/bash

# Smart Traffic Light System - Startup Script
# This script helps you start the system quickly

echo "🚦 Smart Traffic Light System - Starting..."
echo "=============================================="
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found!"
    echo "   Please run this script from the tf_si directory"
    exit 1
fi

# Check Python version
echo "📌 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Python version: $python_version"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "✅ Virtual environment found"
    echo "📌 Activating virtual environment..."
    source venv/bin/activate
else
    echo "⚠️  No virtual environment found"
    echo "   Consider creating one: python3 -m venv venv"
fi

# Check dependencies
echo ""
echo "📌 Checking dependencies..."

check_package() {
    if python3 -c "import $1" 2>/dev/null; then
        echo "   ✅ $1"
        return 0
    else
        echo "   ❌ $1 - NOT INSTALLED"
        return 1
    fi
}

missing_packages=0

check_package "django" || ((missing_packages++))
check_package "cv2" || ((missing_packages++))
check_package "ultralytics" || ((missing_packages++))
check_package "numpy" || ((missing_packages++))

if [ $missing_packages -gt 0 ]; then
    echo ""
    echo "⚠️  Missing $missing_packages package(s)"
    echo "   Install with: pip install -r requirements.txt"
    echo ""
    read -p "   Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📦 Installing dependencies..."
        pip install -r requirements.txt
    else
        echo "❌ Cannot start without dependencies"
        exit 1
    fi
fi

# Check hardware (optional)
echo ""
echo "📌 Checking hardware..."

if python3 -c "from rpi_ws281x import PixelStrip" 2>/dev/null; then
    echo "   ✅ LED strip library (rpi_ws281x)"
else
    echo "   ⚠️  LED strip library not found (OK if not on Raspberry Pi)"
fi

if python3 -c "from picamera2 import Picamera2" 2>/dev/null; then
    echo "   ✅ Camera library (picamera2)"
else
    echo "   ⚠️  Camera library not found (OK if not on Raspberry Pi)"
fi

# Ask for run mode
echo ""
echo "=============================================="
echo "🎮 Select run mode:"
echo "   1) Normal (port 8000)"
echo "   2) With sudo (for LED control)"
echo "   3) Custom port"
echo "   4) Run tests first"
echo "   5) Exit"
echo ""
read -p "Choice (1-5): " choice

case $choice in
    1)
        echo ""
        echo "🚀 Starting server on port 8000..."
        echo "   Dashboard: http://$(hostname -I | awk '{print $1}'):8000/camera/"
        echo ""
        python3 manage.py runserver 0.0.0.0:8000
        ;;
    2)
        echo ""
        echo "🚀 Starting server with sudo (for GPIO access)..."
        echo "   Dashboard: http://$(hostname -I | awk '{print $1}'):8000/camera/"
        echo ""
        sudo python3 manage.py runserver 0.0.0.0:8000
        ;;
    3)
        echo ""
        read -p "Enter port number: " port
        echo ""
        echo "🚀 Starting server on port $port..."
        echo "   Dashboard: http://$(hostname -I | awk '{print $1}'):$port/camera/"
        echo ""
        python3 manage.py runserver 0.0.0.0:$port
        ;;
    4)
        echo ""
        echo "🧪 Running system tests..."
        echo ""
        python3 test_system.py
        
        echo ""
        read -p "Start server after tests? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            echo "🚀 Starting server on port 8000..."
            python3 manage.py runserver 0.0.0.0:8000
        fi
        ;;
    5)
        echo ""
        echo "👋 Goodbye!"
        exit 0
        ;;
    *)
        echo ""
        echo "❌ Invalid choice"
        exit 1
        ;;
esac
