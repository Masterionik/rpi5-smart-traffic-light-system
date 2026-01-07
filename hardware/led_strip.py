import logging

logger = logging.getLogger(__name__)

# Try rpi5_ws2812 first (works on RPi 5), fallback to rpi_ws281x
LED_AVAILABLE = False
LED_LIBRARY = None

try:
    from rpi5_ws2812.ws2812 import WS2812SpiDriver, Color as LEDColor
    LED_AVAILABLE = True
    LED_LIBRARY = 'rpi5_ws2812'
    logger.info("Using rpi5_ws2812 library (RPi 5 compatible)")
except ImportError:
    try:
        from rpi_ws281x import PixelStrip, Color
        LED_AVAILABLE = True
        LED_LIBRARY = 'rpi_ws281x'
        logger.info("Using rpi_ws281x library (RPi 4 compatible)")
    except ImportError:
        logger.warning("No LED library available (rpi5_ws2812 or rpi_ws281x)")


class LEDStripController:
    """
    LED strip controller supporting both RPi 4 and RPi 5
    
    8 LEDs configured as a traffic light:
    - LEDs 0-2 (first 3): RED section
    - LEDs 3-4 (middle 2): YELLOW section  
    - LEDs 5-7 (last 3): GREEN section
    
    Traffic light states:
    - RED: Red section ON, others OFF
    - YELLOW: Yellow section ON, others OFF
    - GREEN: Green section ON, others OFF
    - RED_YELLOW: Red + Yellow sections ON
    """

    # LED segment configuration
    RED_LEDS = [0, 1, 2]      # First 3 LEDs for RED
    YELLOW_LEDS = [3, 4]       # Middle 2 LEDs for YELLOW
    GREEN_LEDS = [5, 6, 7]     # Last 3 LEDs for GREEN
    
    # Colors (will be set with brightness applied)
    COLOR_RED = (255, 0, 0)
    COLOR_YELLOW = (255, 200, 0)
    COLOR_GREEN = (0, 255, 0)
    COLOR_OFF = (0, 0, 0)

    def __init__(self, num_pixels=8, pin=18, freq_hz=800000, dma=10, brightness=64, invert=False, channel=0, spi_bus=0, spi_device=0):
        self.num_pixels = num_pixels
        self.enabled = False
        self._strip = None
        self._driver = None
        self._current_state = 'RED'  # Current traffic light state
        self.brightness = brightness / 255.0 if brightness > 1 else brightness
        
        # Store pixel colors for rpi5_ws2812 (it uses set_all_pixels with a list)
        self._pixel_colors = [(0, 0, 0)] * num_pixels
        
        # For compatibility with traffic controller
        self.leds_per_direction = 2
        self.num_directions = 4
        self.DIRECTIONS = ['NORTH', 'EAST', 'SOUTH', 'WEST']

        if not LED_AVAILABLE:
            logger.warning("No LED library available; LED strip control disabled")
            return

        try:
            if LED_LIBRARY == 'rpi5_ws2812':
                # RPi 5 - Use SPI-based driver
                self._driver = WS2812SpiDriver(spi_bus=spi_bus, spi_device=spi_device, led_count=num_pixels)
                self._strip = self._driver.get_strip()
                self.enabled = True
                logger.info(f"✓ LED strip initialized via SPI (rpi5_ws2812) with {num_pixels} LEDs")
                logger.info(f"  Layout: RED[0-2], YELLOW[3-4], GREEN[5-7]")
            else:
                # RPi 4 - Use PWM-based driver
                from rpi_ws281x import PixelStrip, Color
                self._strip = PixelStrip(
                    num_pixels,
                    pin,
                    freq_hz,
                    dma,
                    invert,
                    brightness,
                    channel,
                )
                self._strip.begin()
                self.enabled = True
                logger.info(f"✓ LED strip initialized via PWM (rpi_ws281x) on pin {pin} with {num_pixels} LEDs")
            
            # Start with RED state
            self.set_state('RED')
                
        except Exception as exc:
            logger.error(f"Failed to initialize LED strip: {exc}")
            import traceback
            logger.error(traceback.format_exc())
            self.enabled = False
            self._strip = None
            self._driver = None

    def _set_pixel(self, index, rgb):
        """Set a single pixel to a color (stored in buffer, call _show to update)"""
        if not self.enabled or self._strip is None:
            return
        
        r, g, b = rgb
        r = int(r * self.brightness)
        g = int(g * self.brightness)
        b = int(b * self.brightness)
        
        # Store in pixel buffer
        if 0 <= index < self.num_pixels:
            self._pixel_colors[index] = (r, g, b)

    def _show(self):
        """Update the LED strip to show changes"""
        if not self.enabled or self._strip is None:
            return
        try:
            if LED_LIBRARY == 'rpi5_ws2812':
                from rpi5_ws2812.ws2812 import Color as LEDColor
                # rpi5_ws2812 only supports set_all_pixels - all LEDs same color
                # Find which color should be shown based on segments
                r, g, b = 0, 0, 0
                
                # Check which segment is active (priority: GREEN > YELLOW > RED)
                for i in self.GREEN_LEDS:
                    pr, pg, pb = self._pixel_colors[i]
                    if pg > 0:  # Green is on
                        r, g, b = pr, pg, pb
                        break
                
                if g == 0:  # No green, check yellow
                    for i in self.YELLOW_LEDS:
                        pr, pg, pb = self._pixel_colors[i]
                        if pr > 0 and pg > 0:  # Yellow is on
                            r, g, b = pr, pg, pb
                            break
                
                if r == 0 and g == 0:  # No yellow, check red
                    for i in self.RED_LEDS:
                        pr, pg, pb = self._pixel_colors[i]
                        if pr > 0:  # Red is on
                            r, g, b = pr, pg, pb
                            break
                
                color = LEDColor(r, g, b)
                self._strip.set_all_pixels(color)
                self._strip.show()
            else:
                from rpi_ws281x import Color
                for i, (r, g, b) in enumerate(self._pixel_colors):
                    self._strip.setPixelColor(i, Color(r, g, b))
                self._strip.show()
        except Exception as e:
            logger.error(f"Error showing LEDs: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def set_state(self, state):
        """
        Set the traffic light state
        
        Args:
            state: 'RED', 'YELLOW', 'GREEN', 'RED_YELLOW', 'OFF'
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
            for i in self.RED_LEDS:
                self._set_pixel(i, self.COLOR_RED)
                
        elif state == 'YELLOW':
            for i in self.YELLOW_LEDS:
                self._set_pixel(i, self.COLOR_YELLOW)
                
        elif state == 'GREEN':
            for i in self.GREEN_LEDS:
                self._set_pixel(i, self.COLOR_GREEN)
                
        elif state == 'RED_YELLOW':
            for i in self.RED_LEDS:
                self._set_pixel(i, self.COLOR_RED)
            for i in self.YELLOW_LEDS:
                self._set_pixel(i, self.COLOR_YELLOW)
                
        elif state == 'OFF':
            pass  # Already turned off
        
        self._show()
        logger.info(f"Traffic light set to {state}")

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
            'OFF': self.COLOR_OFF
        }
        return color_map.get(self._current_state, self.COLOR_OFF)

    def test_sequence(self):
        """Test LED strip with traffic light sequence"""
        import time
        logger.info("Running traffic light test sequence...")
        
        test_states = [
            ("RED", 1.0),
            ("RED_YELLOW", 0.5),
            ("GREEN", 1.0),
            ("YELLOW", 0.5),
            ("RED", 1.0),
            ("OFF", 0.5)
        ]
        
        for state, duration in test_states:
            logger.info(f"Testing {state}...")
            self.set_state(state)
            time.sleep(duration)
        
        logger.info("Traffic light test sequence complete")
