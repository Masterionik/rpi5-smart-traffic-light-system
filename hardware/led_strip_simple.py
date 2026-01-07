import logging

logger = logging.getLogger(__name__)

try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:
    PixelStrip = None
    Color = None


class LEDStripController:
    """
    Simple LED strip controller - all 8 LEDs change together
    Compatible with traffic controller (direction methods control all LEDs)
    """

    def __init__(self, num_pixels=8, pin=18, freq_hz=800000, dma=10, brightness=64, invert=False, channel=0):
        self.num_pixels = num_pixels
        self.enabled = False
        self._strip = None
        self._last_color = (255, 0, 0)
        
        # For compatibility with traffic controller
        self.leds_per_direction = 2
        self.num_directions = 4
        self.DIRECTIONS = ['NORTH', 'EAST', 'SOUTH', 'WEST']

        if PixelStrip is None:
            logger.warning("rpi_ws281x not available; LED strip control disabled")
            return

        try:
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
            logger.info("LED strip initialized on pin %s with %s pixels (SIMPLE MODE - all LEDs together)", pin, num_pixels)
        except Exception as exc:
            logger.error("Failed to initialize LED strip: %s", exc)
            self.enabled = False
            self._strip = None

    def set_color(self, rgb):
        """Set all pixels to the given (r, g, b) tuple."""
        if not self.enabled or self._strip is None:
            return
        r, g, b = rgb
        color = Color(r, g, b)
        for i in range(self.num_pixels):
            self._strip.setPixelColor(i, color)
        self._strip.show()
        self._last_color = rgb

    def set_green(self):
        self.set_color((0, 255, 0))

    def set_red(self):
        self.set_color((255, 0, 0))

    def off(self):
        self.set_color((0, 0, 0))

    def last_color(self):
        return self._last_color
    
    # Traffic controller compatibility methods (all control ALL LEDs)
    def set_direction_state(self, direction, state):
        """Set state for a direction - in simple mode, controls ALL LEDs"""
        state = state.upper() if isinstance(state, str) else state
        
        color_map = {
            'RED': (255, 0, 0),
            'YELLOW': (255, 255, 0),
            'GREEN': (0, 255, 0),
            'RED_YELLOW': (255, 165, 0),
            'OFF': (0, 0, 0)
        }
        
        if state in color_map:
            self.set_color(color_map[state])
            logger.info(f"All LEDs set to {state}")

    def set_all_red(self):
        """Set all LEDs to RED"""
        self.set_red()

    def set_all_green(self):
        """Set all LEDs to GREEN"""
        self.set_green()

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
