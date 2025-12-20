import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:  # Library not installed or not on Pi
    PixelStrip = None
    Color = None


class LEDStripController:
    """
    Advanced LED strip controller for traffic light system
    8 LEDs grouped into 4 directions (2 LEDs per direction)
    
    LED Mapping (8 LEDs total):
    - Direction 0 (North): LEDs 0-1
    - Direction 1 (East):  LEDs 2-3
    - Direction 2 (South): LEDs 4-5
    - Direction 3 (West):  LEDs 6-7
    
    Each direction shows traffic light colors:
    - RED: Both LEDs red
    - YELLOW: Both LEDs yellow
    - GREEN: Both LEDs green
    - RED+YELLOW: Both LEDs orange (transition state)
    """

    # Traffic light colors
    COLOR_RED = (255, 0, 0)
    COLOR_YELLOW = (255, 255, 0)
    COLOR_GREEN = (0, 255, 0)
    COLOR_ORANGE = (255, 165, 0)  # Red+Yellow transition
    COLOR_OFF = (0, 0, 0)
    
    # Direction names
    DIRECTIONS = ['NORTH', 'EAST', 'SOUTH', 'WEST']

    def __init__(self, num_pixels=8, pin=18, freq_hz=800000, dma=10, brightness=64, invert=False, channel=0):
        """
        Initialize LED strip controller
        
        Args:
            num_pixels: Total number of LEDs (default 8)
            pin: GPIO pin (default 18 for PWM)
            brightness: LED brightness 0-255 (default 64 for optimal visibility)
        """
        self.num_pixels = num_pixels
        self.leds_per_direction = 2  # 2 LEDs per traffic direction
        self.num_directions = 4  # 4 directions (N, E, S, W)
        self.enabled = False
        self._strip = None
        self._lock = threading.Lock()
        
        # Current state for each direction
        self._direction_states = {
            0: 'RED',    # North
            1: 'RED',    # East
            2: 'RED',    # South
            3: 'RED'     # West
        }
        
        # Blink state for special effects
        self._blink_active = {i: False for i in range(4)}
        self._blink_thread = None
        self._blink_running = False

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
            
            # Initialize all directions to RED
            self.set_all_red()
            logger.info(f"LED strip initialized on pin {pin} with {num_pixels} pixels")
            logger.info(f"Configuration: {self.num_directions} directions, {self.leds_per_direction} LEDs per direction")
        except Exception as exc:
            logger.error(f"Failed to initialize LED strip: {exc}")
            self.enabled = False

    def _get_led_indices(self, direction):
        """
        Get LED indices for a specific direction
        
        Args:
            direction: Direction index (0=North, 1=East, 2=South, 3=West)
            
        Returns:
            List of LED indices for that direction
        """
        start_idx = direction * self.leds_per_direction
        return list(range(start_idx, start_idx + self.leds_per_direction))

    def _set_direction_color(self, direction, rgb):
        """
        Set color for a specific direction (both LEDs)
        
        Args:
            direction: Direction index (0-3)
            rgb: Tuple (r, g, b)
        """
        if not self.enabled or self._strip is None:
            return
        
        with self._lock:
            r, g, b = rgb
            color = Color(r, g, b)
            
            for led_idx in self._get_led_indices(direction):
                self._strip.setPixelColor(led_idx, color)
            
            self._strip.show()

    def set_direction_state(self, direction, state):
        """
        Set traffic light state for a direction
        
        Args:
            direction: Direction index (0=North, 1=East, 2=South, 3=West)
            state: 'RED', 'YELLOW', 'GREEN', 'RED_YELLOW', 'OFF'
        """
        if direction < 0 or direction >= self.num_directions:
            logger.warning(f"Invalid direction: {direction}")
            return
        
        state = state.upper()
        self._direction_states[direction] = state
        
        color_map = {
            'RED': self.COLOR_RED,
            'YELLOW': self.COLOR_YELLOW,
            'GREEN': self.COLOR_GREEN,
            'RED_YELLOW': self.COLOR_ORANGE,
            'OFF': self.COLOR_OFF
        }
        
        color = color_map.get(state, self.COLOR_RED)
        self._set_direction_color(direction, color)
        
        logger.debug(f"Direction {self.DIRECTIONS[direction]} set to {state}")

    def set_all_red(self):
        """Set all directions to RED"""
        for i in range(self.num_directions):
            self.set_direction_state(i, 'RED')

    def set_all_green(self):
        """Set all directions to GREEN"""
        for i in range(self.num_directions):
            self.set_direction_state(i, 'GREEN')

    def set_all_off(self):
        """Turn off all LEDs"""
        for i in range(self.num_directions):
            self.set_direction_state(i, 'OFF')

    def start_blink(self, direction, color='YELLOW', interval=0.5):
        """
        Start blinking effect for a direction
        
        Args:
            direction: Direction index
            color: Color to blink ('RED', 'YELLOW', 'GREEN')
            interval: Blink interval in seconds
        """
        self._blink_active[direction] = True
        
        if not self._blink_running:
            self._blink_running = True
            self._blink_thread = threading.Thread(
                target=self._blink_worker,
                args=(direction, color, interval),
                daemon=True
            )
            self._blink_thread.start()

    def stop_blink(self, direction):
        """Stop blinking effect for a direction"""
        self._blink_active[direction] = False

    def _blink_worker(self, direction, color, interval):
        """Worker thread for blinking effect"""
        while self._blink_active[direction]:
            self.set_direction_state(direction, color)
            time.sleep(interval)
            self.set_direction_state(direction, 'OFF')
            time.sleep(interval)
        
        self._blink_running = False

    def transition_sequence(self, direction, from_state, to_state):
        """
        Execute smooth transition between traffic light states
        
        Args:
            direction: Direction index
            from_state: Current state ('RED', 'GREEN', etc.)
            to_state: Target state
        """
        # Standard traffic light transitions
        if from_state == 'RED' and to_state == 'GREEN':
            # RED → RED+YELLOW → GREEN
            self.set_direction_state(direction, 'RED_YELLOW')
            time.sleep(1.5)
            self.set_direction_state(direction, 'GREEN')
        
        elif from_state == 'GREEN' and to_state == 'RED':
            # GREEN → YELLOW → RED
            self.set_direction_state(direction, 'YELLOW')
            time.sleep(2.0)
            self.set_direction_state(direction, 'RED')
        
        else:
            # Direct transition
            self.set_direction_state(direction, to_state)

    def get_direction_state(self, direction):
        """Get current state of a direction"""
        return self._direction_states.get(direction, 'RED')

    def get_all_states(self):
        """Get states of all directions"""
        return {
            self.DIRECTIONS[i]: self._direction_states[i]
            for i in range(self.num_directions)
        }

    # Legacy methods for backward compatibility
    def set_color(self, rgb):
        """Set all LEDs to the same color (legacy method)"""
        if not self.enabled or self._strip is None:
            return
        
        with self._lock:
            r, g, b = rgb
            color = Color(r, g, b)
            for i in range(self.num_pixels):
                self._strip.setPixelColor(i, color)
            self._strip.show()

    def set_green(self):
        """Set all LEDs to green (legacy method)"""
        self.set_all_green()

    def set_red(self):
        """Set all LEDs to red (legacy method)"""
        self.set_all_red()

    def off(self):
        """Turn off all LEDs (legacy method)"""
        self.set_all_off()

    def last_color(self):
        """Get last color (legacy method)"""
        return self._direction_states
