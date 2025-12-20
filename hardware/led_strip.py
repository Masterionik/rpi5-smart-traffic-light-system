import logging

logger = logging.getLogger(__name__)

try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:  # Library not installed or not on Pi
    PixelStrip = None
    Color = None


class LEDStripController:
    """Simple wrapper to control an addressable LED strip (e.g., WS2812)"""

    def __init__(self, num_pixels=8, pin=18, freq_hz=800000, dma=10, brightness=64, invert=False, channel=0):
        self.num_pixels = num_pixels
        self.enabled = False
        self._strip = None
        self._last_color = (255, 0, 0)  # default red

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
            logger.info("LED strip initialized on pin %s with %s pixels", pin, num_pixels)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to initialize LED strip: %s", exc)
            self.enabled = False

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
