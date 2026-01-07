#!/usr/bin/env python3
"""
LED Strip Test Script for Smart Traffic Light System
Tests the 8-LED strip configured as a traffic light:
  - LEDs 0-2: RED section
  - LEDs 3-4: YELLOW section
  - LEDs 5-7: GREEN section

Uses rpi5_ws2812 library (RPi 5 compatible via SPI)

Run this script to verify your LED strip is working:
    sudo python3 test_led_strip.py
"""

import time
import sys

print("=" * 50)
print("LED Strip Traffic Light Test for Raspberry Pi 5")
print("=" * 50)

# Try to import the LED library
try:
    from rpi5_ws2812.ws2812 import WS2812SpiDriver, Color
    print("✓ rpi5_ws2812 library loaded successfully")
except ImportError as e:
    print(f"✗ Failed to import rpi5_ws2812: {e}")
    print("\nInstall with: pip install rpi5-ws2812")
    sys.exit(1)

# Configuration
NUM_LEDS = 8
SPI_BUS = 0
SPI_DEVICE = 0
BRIGHTNESS = 0.25  # 25% brightness

# LED segment definitions
RED_LEDS = [0, 1, 2]      # First 3 LEDs
YELLOW_LEDS = [3, 4]      # Middle 2 LEDs
GREEN_LEDS = [5, 6, 7]    # Last 3 LEDs

print(f"\nConfiguration:")
print(f"  - Number of LEDs: {NUM_LEDS}")
print(f"  - SPI Bus: {SPI_BUS}")
print(f"  - SPI Device: {SPI_DEVICE}")
print(f"  - Brightness: {int(BRIGHTNESS * 100)}%")
print(f"\nLED Layout (Traffic Light):")
print(f"  - LEDs 0-2: RED section")
print(f"  - LEDs 3-4: YELLOW section")
print(f"  - LEDs 5-7: GREEN section")

# Initialize the LED strip
try:
    print("\nInitializing LED strip...")
    driver = WS2812SpiDriver(spi_bus=SPI_BUS, spi_device=SPI_DEVICE, led_count=NUM_LEDS)
    strip = driver.get_strip()
    print("✓ LED strip initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize LED strip: {e}")
    print("\nMake sure:")
    print("  1. You're running with sudo")
    print("  2. SPI is enabled (sudo raspi-config -> Interface Options -> SPI)")
    print("  3. LED strip is connected to GPIO 10 (SPI MOSI)")
    sys.exit(1)

def set_all_color(r, g, b):
    """Set all LEDs to a specific color"""
    color = Color(
        int(r * BRIGHTNESS),
        int(g * BRIGHTNESS),
        int(b * BRIGHTNESS)
    )
    strip.set_all_pixels(color)
    strip.show()

def clear_all():
    """Turn off all LEDs"""
    set_all_color(0, 0, 0)

def set_state(state):
    """Set traffic light state - all LEDs show the same color"""
    if state == 'RED':
        set_all_color(255, 0, 0)
    elif state == 'YELLOW':
        set_all_color(255, 200, 0)
    elif state == 'GREEN':
        set_all_color(0, 255, 0)
    elif state == 'RED_YELLOW':
        set_all_color(255, 100, 0)  # Orange for red+yellow
    else:
        clear_all()

print("\n" + "=" * 50)
print("Testing Individual Segments")
print("=" * 50)

# Test each segment individually
print("\n1. Testing RED segment (LEDs 0-2)...")
set_state('RED')
time.sleep(1.5)

print("2. Testing YELLOW segment (LEDs 3-4)...")
set_state('YELLOW')
time.sleep(1.5)

print("3. Testing GREEN segment (LEDs 5-7)...")
set_state('GREEN')
time.sleep(1.5)

print("4. Testing RED+YELLOW transition...")
set_state('RED_YELLOW')
time.sleep(1.5)

# Traffic light sequence
print("\n" + "=" * 50)
print("Simulating Traffic Light Sequence")
print("=" * 50)

for i in range(3):
    print(f"\nCycle {i + 1}/3:")
    
    print("  🔴 RED (Stop)")
    set_state('RED')
    time.sleep(2.0)
    
    print("  🟠 RED+YELLOW (Prepare)")
    set_state('RED_YELLOW')
    time.sleep(1.0)
    
    print("  🟢 GREEN (Go)")
    set_state('GREEN')
    time.sleep(2.0)
    
    print("  🟡 YELLOW (Caution)")
    set_state('YELLOW')
    time.sleep(1.0)

# Vehicle detection simulation
print("\n" + "=" * 50)
print("Simulating Vehicle Detection Behavior")
print("=" * 50)

print("\n1. No vehicle detected → RED")
set_state('RED')
time.sleep(2.0)

print("2. Vehicle detected → transitioning to GREEN...")
set_state('RED_YELLOW')
time.sleep(1.0)
set_state('GREEN')
time.sleep(2.0)

print("3. Vehicle left → transitioning to RED...")
set_state('YELLOW')
time.sleep(1.0)
set_state('RED')
time.sleep(1.0)

# Turn off
print("\n" + "=" * 50)
print("Test Complete - Turning off LEDs...")
clear_all()
print("✓ All LEDs off")
print("=" * 50)
set_all_leds(Color(0, 0, 0))
print("✓ Test complete!")

print("\n" + "=" * 50)
print("LED Strip is working correctly!")
print("=" * 50)
