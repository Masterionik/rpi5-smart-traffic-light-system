#!/usr/bin/env python3
"""
Test script for LED strip with individual pixel control
Uses adafruit-circuitpython-neopixel library

Installation:
    sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel

Usage:
    sudo python3 test_led_strip.py
"""

import time
import sys

print("=" * 50)
print("LED Strip Test - Individual Pixel Control")
print("=" * 50)

# Try importing the libraries
try:
    import board
    import neopixel
    print("✓ NeoPixel library imported successfully")
except ImportError as e:
    print(f"✗ Failed to import neopixel: {e}")
    print("\nInstall with:")
    print("  sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel")
    sys.exit(1)

# Setup - GPIO18, 8 LEDs
NUM_LEDS = 8
print(f"\nInitializing {NUM_LEDS} LEDs on GPIO18...")

try:
    pixels = neopixel.NeoPixel(board.D10, NUM_LEDS, brightness=0.3, auto_write=False)
    print("✓ NeoPixel strip initialized on GPIO10 (SPI)")
except Exception as e:
    print(f"✗ Failed to initialize: {e}")
    print("\nMake sure to run with sudo!")
    sys.exit(1)

# Test 1: Individual pixel control
print("\n--- Test 1: Individual Pixel Control ---")
print("Lighting each LED one by one...")

colors = [
    ((255, 0, 0), "Red"),
    ((0, 255, 0), "Green"),
    ((0, 0, 255), "Blue"),
    ((255, 255, 0), "Yellow"),
    ((255, 0, 255), "Magenta"),
    ((0, 255, 255), "Cyan"),
    ((255, 255, 255), "White"),
    ((255, 128, 0), "Orange"),
]

for i in range(NUM_LEDS):
    # Turn off all LEDs
    pixels.fill((0, 0, 0))
    
    # Light only this LED
    color, name = colors[i % len(colors)]
    pixels[i] = color
    pixels.show()
    
    print(f"  LED {i}: {name} {color}")
    time.sleep(0.5)

# Test 2: Traffic light segments
print("\n--- Test 2: Traffic Light Segments ---")

# Layout:
# LEDs 0-2: RED section
# LEDs 3-4: YELLOW section
# LEDs 5-7: GREEN section

def show_red():
    pixels.fill((0, 0, 0))
    pixels[0] = (255, 0, 0)
    pixels[1] = (255, 0, 0)
    pixels[2] = (255, 0, 0)
    pixels.show()
    print("  🔴 RED section ON (LEDs 0-2)")

def show_yellow():
    pixels.fill((0, 0, 0))
    pixels[3] = (255, 255, 0)
    pixels[4] = (255, 255, 0)
    pixels.show()
    print("  🟡 YELLOW section ON (LEDs 3-4)")

def show_green():
    pixels.fill((0, 0, 0))
    pixels[5] = (0, 255, 0)
    pixels[6] = (0, 255, 0)
    pixels[7] = (0, 255, 0)
    pixels.show()
    print("  🟢 GREEN section ON (LEDs 5-7)")

def show_all():
    # Red section
    pixels[0] = (255, 0, 0)
    pixels[1] = (255, 0, 0)
    pixels[2] = (255, 0, 0)
    # Yellow section
    pixels[3] = (255, 255, 0)
    pixels[4] = (255, 255, 0)
    # Green section
    pixels[5] = (0, 255, 0)
    pixels[6] = (0, 255, 0)
    pixels[7] = (0, 255, 0)
    pixels.show()
    print("  🚦 ALL sections ON")

# Run traffic light sequence
print("\nRunning traffic light sequence...")

show_all()
time.sleep(2)

for cycle in range(2):
    print(f"\n  Cycle {cycle + 1}:")
    show_red()
    time.sleep(2)
    
    # Red + Yellow (transition to green)
    pixels[3] = (255, 255, 0)
    pixels[4] = (255, 255, 0)
    pixels.show()
    print("  🔴🟡 RED + YELLOW (get ready)")
    time.sleep(1)
    
    show_green()
    time.sleep(2)
    
    show_yellow()
    time.sleep(1)

# Turn off all LEDs
print("\n--- Turning off all LEDs ---")
pixels.fill((0, 0, 0))
pixels.show()
print("✓ All LEDs off")

print("\n" + "=" * 50)
print("✓ LED Strip Test Complete!")
print("=" * 50)
print("\nIndividual pixel control: WORKING ✓")
print("Traffic light segments: WORKING ✓")
