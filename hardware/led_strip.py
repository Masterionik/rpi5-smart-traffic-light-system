"""
LED Strip Controller using Adafruit NeoPixel library
Supports individual pixel control for traffic light semaphore

Raspberry Pi 5: Uses GPIO10 (SPI MOSI) for NeoPixel
Installation: sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel --break-system-packages

Must run with sudo for GPIO access!
"""

import logging

logger = logging.getLogger(__name__)

# Try to import neopixel library
LED_AVAILABLE = False
LED_LIBRARY = None

try:
    import board
    import neopixel
    LED_AVAILABLE = True
    LED_LIBRARY = 'neopixel'
    logger.info("Using adafruit-circuitpython-neopixel library")
except ImportError:
    try:
        from rpi_ws281x import PixelStrip, Color
        LED_AVAILABLE = True
        LED_LIBRARY = 'rpi_ws281x'
        logger.info("Using rpi_ws281x library (fallback)")
    except ImportError:
        logger.warning("No LED library available. Install with: sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel --break-system-packages")


class LEDStripController:
    """
    LED strip controller with INDIVIDUAL PIXEL CONTROL
    
    8 LEDs configured as a traffic light semaphore:
    - LEDs 0-2 (first 3): RED section
    - LEDs 3-4 (middle 2): YELLOW section  
    - LEDs 5-7 (last 3): GREEN section
    
    Traffic light states:
    - RED: Red section ON, others OFF
    - YELLOW: Yellow section ON, others OFF
    - GREEN: Green section ON, others OFF
    - RED_YELLOW: Red + Yellow sections ON (transition state)
    - ALL_ON: All sections lit in their respective colors (test mode)
    """

    # LED segment configuration
    RED_LEDS = [0, 1, 2]      # First 3 LEDs for RED
    YELLOW_LEDS = [3, 4]       # Middle 2 LEDs for YELLOW
    GREEN_LEDS = [5, 6, 7]     # Last 3 LEDs for GREEN
    
    # Colors (RGB tuples)
    COLOR_RED = (255, 0, 0)
    COLOR_YELLOW = (255, 255, 0)  # True yellow = Red + Green
    COLOR_GREEN = (0, 255, 0)
    COLOR_OFF = (0, 0, 0)

    def __init__(self, num_pixels=8, pin=18, brightness=64, **kwargs):
        """
        Initialize LED strip controller
        
        Args:
            num_pixels: Number of LEDs (default 8)
            pin: GPIO pin (default 18 for D18)
            brightness: LED brightness 0-255 (default 64)
        """
        self.num_pixels = num_pixels
        self.enabled = False
        self._pixels = None
        self._current_state = 'RED'
        self.brightness = brightness / 255.0 if brightness > 1 else brightness
        
        # For compatibility with traffic controller
        self.leds_per_direction = 2
        self.num_directions = 4
        self.DIRECTIONS = ['NORTH', 'EAST', 'SOUTH', 'WEST']

        if not LED_AVAILABLE:
            logger.warning("No LED library available; LED strip control disabled")
            logger.warning("Install with: sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel")
            return

        try:
            if LED_LIBRARY == 'neopixel':
                # Use adafruit-circuitpython-neopixel (SUPPORTS INDIVIDUAL PIXELS!)
                # RPi 5 uses GPIO10 (SPI MOSI), not GPIO18!
                self._pixels = neopixel.NeoPixel(
                    board.D10,  # GPIO10 for Raspberry Pi 5 SPI
                    num_pixels,
                    brightness=self.brightness,
                    auto_write=False  # Manual control for better performance
                )
                self.enabled = True
                logger.info(f"✓ LED strip initialized with NeoPixel on GPIO10 (SPI), {num_pixels} LEDs")
                logger.info(f"  Layout: RED[0-2], YELLOW[3-4], GREEN[5-7]")
                logger.info(f"  Individual pixel control: ENABLED ✓")
            else:
                # Fallback to rpi_ws281x
                from rpi_ws281x import PixelStrip, Color
                self._pixels = PixelStrip(
                    num_pixels,
                    pin,
                    800000,  # freq_hz
                    10,      # dma
                    False,   # invert
                    brightness,
                    0,       # channel
                )
                self._pixels.begin()
                self.enabled = True
                logger.info(f"✓ LED strip initialized with rpi_ws281x on GPIO{pin}, {num_pixels} LEDs")
            
            # Start with RED state
            self.set_state('RED')
                
        except Exception as exc:
            logger.error(f"Failed to initialize LED strip: {exc}")
            import traceback
            logger.error(traceback.format_exc())
            self.enabled = False
            self._pixels = None

    def _set_pixel(self, index, color):
        """Set a single pixel to a color"""
        if not self.enabled or self._pixels is None:
            return
        
        if 0 <= index < self.num_pixels:
            # Apply brightness to color
            r, g, b = color
            r = int(r * self.brightness)
            g = int(g * self.brightness)
            b = int(b * self.brightness)
            
            if LED_LIBRARY == 'neopixel':
                self._pixels[index] = (r, g, b)
            else:
                from rpi_ws281x import Color
                self._pixels.setPixelColor(index, Color(r, g, b))

    def _show(self):
        """Update the LED strip to display current pixel values"""
        if not self.enabled or self._pixels is None:
            return
        try:
            if LED_LIBRARY == 'neopixel':
                self._pixels.show()
            else:
                self._pixels.show()
        except Exception as e:
            logger.error(f"Error updating LEDs: {e}")

    def set_state(self, state):
        """
        Set the traffic light state
        
        Args:
            state: 'RED', 'YELLOW', 'GREEN', 'RED_YELLOW', 'ALL_ON', 'OFF'
        """
        if not self.enabled:
            logger.debug(f"LED set_state({state}) called but strip not enabled")
            return
        
        state = str(state).upper()
        self._current_state = state
        
        # Turn off all LEDs first
        for i in range(self.num_pixels):
            self._set_pixel(i, self.COLOR_OFF)
        
        # Set appropriate segments based on state
        if state == 'RED':
            # Only RED section lit
            for i in self.RED_LEDS:
                self._set_pixel(i, self.COLOR_RED)
                
        elif state == 'YELLOW':
            # Only YELLOW section lit
            for i in self.YELLOW_LEDS:
                self._set_pixel(i, self.COLOR_YELLOW)
                
        elif state == 'GREEN':
            # Only GREEN section lit
            for i in self.GREEN_LEDS:
                self._set_pixel(i, self.COLOR_GREEN)
                
        elif state == 'RED_YELLOW':
            # Both RED and YELLOW sections lit (transition)
            for i in self.RED_LEDS:
                self._set_pixel(i, self.COLOR_RED)
            for i in self.YELLOW_LEDS:
                self._set_pixel(i, self.COLOR_YELLOW)
                
        elif state == 'ALL_ON':
            # All sections lit in their respective colors (test mode)
            for i in self.RED_LEDS:
                self._set_pixel(i, self.COLOR_RED)
            for i in self.YELLOW_LEDS:
                self._set_pixel(i, self.COLOR_YELLOW)
            for i in self.GREEN_LEDS:
                self._set_pixel(i, self.COLOR_GREEN)
                
        elif state == 'OFF':
            pass  # Already turned off above
        
        self._show()
        logger.info(f"🚦 Traffic light: {state}")

    def set_green(self):
        """Set traffic light to GREEN"""
        self.set_state('GREEN')

    def set_red(self):
        """Set traffic light to RED"""
        self.set_state('RED')

    def set_yellow(self):
        """Set traffic light to YELLOW"""
        self.set_state('YELLOW')

    def off(self):
        """Turn off all LEDs"""
        self.set_state('OFF')

    def get_state(self):
        """Get current traffic light state"""
        return self._current_state
    
    def fill(self, color):
        """Fill all LEDs with the same color"""
        if not self.enabled or self._pixels is None:
            return
        
        for i in range(self.num_pixels):
            self._set_pixel(i, color)
        self._show()
    
    # Traffic controller compatibility methods
    def set_direction_state(self, direction, state):
        """Set state - in single-camera mode, controls the traffic light"""
        self.set_state(state)

    def set_all_red(self):
        """Set traffic light to RED"""
        self.set_red()

    def set_all_green(self):
        """Set traffic light to GREEN"""
        self.set_green()

    def set_all_yellow(self):
        """Set traffic light to YELLOW"""
        self.set_yellow()

    def set_all_off(self):
        """Turn off all LEDs"""
        self.off()

    def get_direction_state(self, direction):
        """Get current state"""
        return self._current_state

    def get_all_states(self):
        """Get states of all directions - all same in single-camera mode"""
        return {
            'NORTH': self._current_state,
            'EAST': self._current_state,
            'SOUTH': self._current_state,
            'WEST': self._current_state
        }

    def last_color(self):
        """Get the last color that was set (for backward compatibility)"""
        color_map = {
            'RED': self.COLOR_RED,
            'YELLOW': self.COLOR_YELLOW,
            'GREEN': self.COLOR_GREEN,
            'RED_YELLOW': (255, 165, 0),
            'ALL_ON': (255, 255, 255),
            'OFF': self.COLOR_OFF
        }
        return color_map.get(self._current_state, self.COLOR_OFF)

    def test_sequence(self):
        """Test LED strip with traffic light sequence"""
        import time
        logger.info("🚦 Running traffic light test sequence...")
        
        test_states = [
            ("ALL_ON", 2.0),    # All colors visible - verify all LEDs work
            ("RED", 1.5),       # Red section only
            ("RED_YELLOW", 0.5), # Red + Yellow
            ("GREEN", 1.5),     # Green section only
            ("YELLOW", 0.5),    # Yellow section only
            ("RED", 1.0),       # Back to red
            ("OFF", 0.5)        # All off
        ]
        
        for state, duration in test_states:
            logger.info(f"  Testing {state}...")
            self.set_state(state)
            time.sleep(duration)
        
        # End in RED (safe state)
        self.set_state('RED')
        logger.info("✓ Traffic light test sequence complete")

    def test_individual_pixels(self):
        """Test individual pixel control - lights each LED one by one"""
        import time
        logger.info("🔬 Testing individual pixel control...")
        
        colors = [
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 255, 255), # White
            (255, 128, 0),  # Orange
        ]
        
        # Light each LED individually
        for i in range(self.num_pixels):
            # Turn off all LEDs
            for j in range(self.num_pixels):
                self._set_pixel(j, (0, 0, 0))
            
            # Light only this LED
            self._set_pixel(i, colors[i % len(colors)])
            self._show()
            logger.info(f"  LED {i}: {colors[i % len(colors)]}")
            time.sleep(0.5)
        
        # Show all LEDs with their segment colors
        self.set_state('ALL_ON')
        logger.info("✓ Individual pixel test complete - all segments lit")
