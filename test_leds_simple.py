#!/usr/bin/env python3
"""
Simple LED Test Script - Test individual pixel control
Run with: sudo python3 test_leds_simple.py
"""

import time

print("=" * 50)
print("LED Strip Test - Individual Pixel Control")
print("=" * 50)

# Try different libraries
pixels = None
library_used = None

# Method 1: Try adafruit neopixel
try:
    import board
    import neopixel
    pixels = neopixel.NeoPixel(board.D18, 8, brightness=0.3, auto_write=True)
    library_used = "neopixel"
    print("✓ Using: adafruit-circuitpython-neopixel")
except Exception as e:
    print(f"✗ neopixel failed: {e}")

# Method 2: Try rpi_ws281x
if pixels is None:
    try:
        from rpi_ws281x import PixelStrip, Color
        strip = PixelStrip(8, 18, 800000, 10, False, 64, 0)
        strip.begin()
        
        # Wrapper class to make it work like neopixel
        class PixelWrapper:
            def __init__(self, strip):
                self.strip = strip
            def __setitem__(self, i, color):
                r, g, b = color
                self.strip.setPixelColor(i, Color(r, g, b))
                self.strip.show()
            def fill(self, color):
                r, g, b = color
                for i in range(8):
                    self.strip.setPixelColor(i, Color(r, g, b))
                self.strip.show()
        
        pixels = PixelWrapper(strip)
        library_used = "rpi_ws281x"
        print("✓ Using: rpi_ws281x")
    except Exception as e:
        print(f"✗ rpi_ws281x failed: {e}")

# Method 3: Try rpi5-ws2812 with SPI
if pixels is None:
    try:
        from rpi5_ws2812.ws2812 import WS2812SpiDriver, Color as LEDColor
        driver = WS2812SpiDriver(spi_bus=0, spi_device=0, led_count=8)
        strip = driver.get_strip()
        
        # This library only supports set_all_pixels - NO individual control
        class SpiWrapper:
            def __init__(self, strip):
                self.strip = strip
                self.colors = [(0,0,0)] * 8
            def __setitem__(self, i, color):
                self.colors[i] = color
                # Can only set all same color - use the last set color
                r, g, b = color
                self.strip.set_all_pixels(LEDColor(r, g, b))
                self.strip.show()
            def fill(self, color):
                r, g, b = color
                self.strip.set_all_pixels(LEDColor(r, g, b))
                self.strip.show()
        
        pixels = SpiWrapper(strip)
        library_used = "rpi5_ws2812 (SPI - NO individual control!)"
        print(f"⚠ Using: {library_used}")
    except Exception as e:
        print(f"✗ rpi5_ws2812 failed: {e}")

if pixels is None:
    print("\n❌ No LED library available!")
    print("\nInstall one of these:")
    print("  pip install adafruit-circuitpython-neopixel")
    print("  pip install rpi_ws281x")
    print("  pip install rpi5-ws2812")
    exit(1)

print(f"\n✓ Library: {library_used}")
print("=" * 50)

# Test 1: Light each LED individually with different colors
print("\n--- Test 1: Individual LEDs ---")
colors = [
    ((255, 0, 0), "RED"),
    ((0, 255, 0), "GREEN"),
    ((0, 0, 255), "BLUE"),
    ((255, 255, 0), "YELLOW"),
    ((255, 0, 255), "MAGENTA"),
    ((0, 255, 255), "CYAN"),
    ((255, 255, 255), "WHITE"),
    ((255, 128, 0), "ORANGE"),
]

for i in range(8):
    # Turn off all
    pixels.fill((0, 0, 0))
    time.sleep(0.1)
    
    # Light this LED
    color, name = colors[i]
    pixels[i] = color
    print(f"  LED {i}: {name}")
    time.sleep(0.5)

# Test 2: Traffic light segments
print("\n--- Test 2: Traffic Light Semaphore ---")

# Turn off all
pixels.fill((0, 0, 0))
time.sleep(0.5)

# RED section (LEDs 0-2)
print("  🔴 RED section (LEDs 0, 1, 2)")
pixels[0] = (255, 0, 0)
pixels[1] = (255, 0, 0)
pixels[2] = (255, 0, 0)
time.sleep(2)

# Turn off, then YELLOW section (LEDs 3-4)
pixels.fill((0, 0, 0))
print("  🟡 YELLOW section (LEDs 3, 4)")
pixels[3] = (255, 255, 0)
pixels[4] = (255, 255, 0)
time.sleep(2)

# Turn off, then GREEN section (LEDs 5-7)
pixels.fill((0, 0, 0))
print("  🟢 GREEN section (LEDs 5, 6, 7)")
pixels[5] = (0, 255, 0)
pixels[6] = (0, 255, 0)
pixels[7] = (0, 255, 0)
time.sleep(2)

# Test 3: All sections at once (semaphore test)
print("\n--- Test 3: Full Semaphore (all sections) ---")
pixels.fill((0, 0, 0))
pixels[0] = (255, 0, 0)
pixels[1] = (255, 0, 0)
pixels[2] = (255, 0, 0)
pixels[3] = (255, 255, 0)
pixels[4] = (255, 255, 0)
pixels[5] = (0, 255, 0)
pixels[6] = (0, 255, 0)
pixels[7] = (0, 255, 0)
print("  🚦 All sections lit!")
time.sleep(3)

# Turn off
print("\n--- Turning off ---")
pixels.fill((0, 0, 0))

print("\n" + "=" * 50)
print("✓ Test Complete!")
print("=" * 50)

if "individual" in library_used.lower() or library_used in ["neopixel", "rpi_ws281x"]:
    print("\n✅ Individual pixel control: WORKING")
else:
    print("\n⚠️  Individual pixel control: NOT SUPPORTED")
    print("   The rpi5_ws2812 library can only set all LEDs to same color")
