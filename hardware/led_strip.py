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
    - RPi 5: Uses rpi5_ws2812 (SPI-based)
    - RPi 4: Uses rpi_ws281x (PWM-based)
    All 8 LEDs change together for simple traffic light simulation
    """

    def __init__(self, num_pixels=8, pin=18, freq_hz=800000, dma=10, brightness=64, invert=False, channel=0, spi_bus=0, spi_device=0):
        self.num_pixels = num_pixels
        self.enabled = False
        self._strip = None
        self._driver = None
        self._last_color = (255, 0, 0)
        self.brightness = brightness / 255.0 if brightness > 1 else brightness
        
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
                self.set_color(self._last_color)
                logger.info(f"✓ LED strip initialized via SPI (rpi5_ws2812) with {num_pixels} LEDs")
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
                self.set_color(self._last_color)
                logger.info(f"✓ LED strip initialized via PWM (rpi_ws281x) on pin {pin} with {num_pixels} LEDs")
                
        except Exception as exc:
            logger.error(f"Failed to initialize LED strip: {exc}")
            import traceback
            logger.error(traceback.format_exc())
            self.enabled = False
            self._strip = None
            self._driver = None

    def set_color(self, rgb):
        """Set all pixels to the given (r, g, b) tuple."""
        if not self.enabled or self._strip is None:
            logger.debug(f"LED set_color called but strip not enabled (enabled={self.enabled}, strip={self._strip})")
            return
            
        r, g, b = rgb
        
        try:
            if LED_LIBRARY == 'rpi5_ws2812':
                # rpi5_ws2812 library
                from rpi5_ws2812.ws2812 import Color as LEDColor
                color = LEDColor(
                    int(r * self.brightness),
                    int(g * self.brightness),
                    int(b * self.brightness)
                )
                self._strip.set_all_pixels(color)
                self._strip.show()
            else:
                # rpi_ws281x library
                from rpi_ws281x import Color
                color = Color(
                    int(r * self.brightness),
                    int(g * self.brightness),
                    int(b * self.brightness)
                )
                for i in range(self.num_pixels):
                    self._strip.setPixelColor(i, color)
                self._strip.show()
                
            self._last_color = rgb
            logger.debug(f"LED color set to RGB{rgb}")
            
        except Exception as e:
            logger.error(f"Error setting LED color: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def set_green(self):
        """Set all LEDs to green"""
        self.set_color((0, 255, 0))

    def set_red(self):
        """Set all LEDs to red"""
        self.set_color((255, 0, 0))

    def set_yellow(self):
        """Set all LEDs to yellow"""
        self.set_color((255, 255, 0))

    def off(self):
        """Turn off all LEDs"""
        self.set_color((0, 0, 0))

    def last_color(self):
        """Get the last color that was set"""
        return self._last_color
    
    # Traffic controller compatibility methods
    def set_direction_state(self, direction, state):
        """Set state for a direction - in simple mode, controls ALL LEDs"""
        state = str(state).upper()
        
        color_map = {
            'RED': (255, 0, 0),
            'YELLOW': (255, 255, 0),
            'GREEN': (0, 255, 0),
            'RED_YELLOW': (255, 165, 0),  # Orange for red+yellow
            'OFF': (0, 0, 0)
        }
        
        if state in color_map:
            self.set_color(color_map[state])
            logger.info(f"LED strip set to {state}")

    def set_all_red(self):
        """Set all LEDs to RED"""
        self.set_red()

    def set_all_green(self):
        """Set all LEDs to GREEN"""
        self.set_green()

    def set_all_yellow(self):
        """Set all LEDs to YELLOW"""
        self.set_yellow()

    def set_all_off(self):
        """Turn off all LEDs"""
        self.off()

    def get_direction_state(self, direction):
        """Get current state - returns based on last color"""
        if self._last_color == (255, 0, 0):
            return 'RED'
        elif self._last_color == (0, 255, 0):
            return 'GREEN'
        elif self._last_color == (255, 255, 0):
            return 'YELLOW'
        elif self._last_color == (255, 165, 0):
            return 'RED_YELLOW'
        else:
            return 'OFF'

    def get_all_states(self):
        """Get states of all directions - all same in simple mode"""
        state = self.get_direction_state(0)
        return {
            'NORTH': state,
            'EAST': state,
            'SOUTH': state,
            'WEST': state
        }

    def test_sequence(self):
        """Test LED strip with a color sequence"""
        import time
        logger.info("Running LED test sequence...")
        
        test_colors = [
            ((255, 0, 0), "RED"),
            ((255, 255, 0), "YELLOW"),
            ((0, 255, 0), "GREEN"),
            ((0, 0, 255), "BLUE"),
            ((255, 255, 255), "WHITE"),
            ((0, 0, 0), "OFF")
        ]
        
        for color, name in test_colors:
            logger.info(f"Testing {name}...")
            self.set_color(color)
            time.sleep(0.5)
        
        logger.info("LED test sequence complete")
