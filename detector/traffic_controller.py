"""
Traffic Light Control Algorithm
Supports both SIMPLE mode (immediate response) and AUTO mode (intelligent cycling)
"""

import threading
import time
import logging
from collections import deque
from datetime import datetime, time as dt_time

logger = logging.getLogger(__name__)


def log_to_database(event_type, message, direction=None, vehicle_count=0, led_state=None, triggered_by='AUTO'):
    """
    Log events to Django database
    Safe to call even when Django isn't fully loaded
    """
    try:
        from detection.models import DetectionEvent, TrafficLightState, VehicleCount
        
        # Log detection event
        DetectionEvent.objects.create(
            event_type=event_type,
            direction=direction,
            message=message,
            vehicle_count=vehicle_count
        )
        
        # Log LED state change if applicable
        if led_state:
            TrafficLightState.objects.create(
                state=led_state,
                direction=direction,
                triggered_by=triggered_by
            )
            
    except Exception as e:
        logger.debug(f"Could not log to database: {e}")


class TrafficController:
    """
    Traffic light controller with multiple modes
    
    Modes:
    - SIMPLE: Immediate response to vehicle detection (car → GREEN, no car → RED)
    - AUTO: Intelligent cycling with dynamic timing
    - MANUAL: Manual control through API
    
    LED Layout (8 LEDs configured as traffic light):
    - LEDs 0-2: RED section
    - LEDs 3-4: YELLOW section
    - LEDs 5-7: GREEN section
    """
    
    # Timing constants (seconds)
    T_MIN = 10   # Minimum green time
    T_MAX = 60   # Maximum green time
    T_YELLOW = 2  # Yellow light duration
    T_RED_YELLOW = 1.5  # Red+Yellow transition
    T_PEDESTRIAN = 15  # Pedestrian green time
    T_PEDESTRIAN_COOLDOWN = 30  # Cooldown between pedestrian requests
    
    # Simple mode settings
    SIMPLE_GREEN_DURATION = 5  # Seconds to show green after detection
    SIMPLE_YELLOW_DURATION = 2  # Seconds to show yellow before red
    
    # Directions
    DIRECTIONS = ['NORTH', 'EAST', 'SOUTH', 'WEST']
    
    def __init__(self, led_controller):
        """
        Initialize traffic controller
        
        Args:
            led_controller: LEDStripController instance
        """
        self.led_controller = led_controller
        
        # Current system state
        self.current_direction = 0  # Index of current green direction
        self.current_state = 'RED'  # Current traffic light state
        self.mode = 'SIMPLE'  # SIMPLE, AUTO, or MANUAL (default to SIMPLE for immediate response)
        self.running = False
        
        # Vehicle counts per direction
        self.vehicle_counts = {direction: 0 for direction in self.DIRECTIONS}
        self.previous_counts = {direction: 0 for direction in self.DIRECTIONS}  # Track changes
        
        # Simple mode state
        self._last_detection_time = 0
        self._simple_state = 'RED'
        self._transition_lock = threading.Lock()
        
        # Waiting time tracking (cycles waiting)
        self.waiting_cycles = {direction: 0 for direction in self.DIRECTIONS}
        
        # Pedestrian requests
        self.pedestrian_requests = {direction: False for direction in self.DIRECTIONS}
        self.pedestrian_last_served = {direction: 0 for direction in self.DIRECTIONS}
        
        # Statistics
        self.stats = {
            'total_vehicles_processed': 0,
            'average_wait_time': 0,
            'green_time_efficiency': 0,
            'pedestrian_requests_served': 0,
            'cycle_count': 0
        }
        
        # Event log
        self.event_log = deque(maxlen=1000)
        
        # Control thread
        self.control_thread = None
        self.lock = threading.Lock()
        
    def start(self):
        """Start automatic traffic control"""
        if self.running:
            logger.warning("Traffic controller already running")
            return
        
        self.running = True
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()
        
        self._log_event("SYSTEM", "Traffic controller started")
        logger.info("Traffic controller started")
    
    def stop(self):
        """Stop traffic control"""
        self.running = False
        if self.control_thread:
            self.control_thread.join(timeout=5)
        
        # Set all to red
        self.led_controller.set_all_red()
        
        self._log_event("SYSTEM", "Traffic controller stopped")
        logger.info("Traffic controller stopped")
    
    def update_vehicle_counts(self, counts_dict):
        """
        Update vehicle counts from detection system
        In SIMPLE mode, triggers immediate LED response
        
        Args:
            counts_dict: Dict with keys 'NORTH', 'EAST', 'SOUTH', 'WEST'
        """
        with self.lock:
            # Store previous counts for comparison
            old_total = sum(self.vehicle_counts.values())
            
            for direction in self.DIRECTIONS:
                if direction in counts_dict:
                    old_count = self.vehicle_counts[direction]
                    new_count = counts_dict[direction]
                    self.vehicle_counts[direction] = new_count
                    
                    # Log significant changes to database
                    if new_count != old_count:
                        if new_count > old_count:
                            log_to_database('CAR', f"Vehicle detected in {direction}", direction, new_count, triggered_by='DETECTION')
                        # Don't log vehicle leaving for less spam
            
            new_total = sum(self.vehicle_counts.values())
        
        # SIMPLE mode: Immediate LED response based on detection
        if self.mode == 'SIMPLE':
            self._handle_simple_mode_detection(old_total, new_total)
    
    def _handle_simple_mode_detection(self, old_total, new_total):
        """
        Handle LED changes in SIMPLE mode
        
        Logic:
        - Vehicles detected (total > 0): Show GREEN
        - No vehicles (total = 0): Show RED
        - Transitions through YELLOW for safety
        """
        with self._transition_lock:
            current_time = time.time()
            
            if new_total > 0:
                # Vehicles detected - should be GREEN
                if self._simple_state != 'GREEN':
                    # Transition to green
                    if self._simple_state == 'RED':
                        # RED -> RED_YELLOW -> GREEN
                        logger.info(f"🚗 Vehicle detected ({new_total} total) - switching to GREEN")
                        self.led_controller.set_state('RED_YELLOW')
                        self._simple_state = 'RED_YELLOW'
                        self.current_state = 'RED_YELLOW'
                        
                        # Short delay then green
                        threading.Timer(1.0, self._set_simple_green).start()
                        
                    elif self._simple_state == 'YELLOW':
                        # If transitioning to red, cancel and go back to green
                        logger.info(f"🚗 Vehicle still detected - staying GREEN")
                        self.led_controller.set_state('GREEN')
                        self._simple_state = 'GREEN'
                        self.current_state = 'GREEN'
                        
                self._last_detection_time = current_time
                log_to_database('LED_CHANGE', f"GREEN - {new_total} vehicles", None, new_total, 'GREEN', 'DETECTION')
                    
            else:
                # No vehicles - should be RED (after timeout)
                if self._simple_state == 'GREEN':
                    # Only go to yellow if enough time has passed since last detection
                    time_since_detection = current_time - self._last_detection_time
                    if time_since_detection >= self.SIMPLE_GREEN_DURATION:
                        logger.info("🚫 No vehicles detected - switching to RED")
                        self.led_controller.set_state('YELLOW')
                        self._simple_state = 'YELLOW'
                        self.current_state = 'YELLOW'
                        
                        # After yellow, go to red
                        threading.Timer(self.SIMPLE_YELLOW_DURATION, self._set_simple_red).start()
                        log_to_database('LED_CHANGE', 'YELLOW - transitioning to RED', None, 0, 'YELLOW', 'AUTO')
    
    def _set_simple_green(self):
        """Set LED to GREEN in simple mode (called after transition)"""
        with self._transition_lock:
            if self._simple_state == 'RED_YELLOW':
                self.led_controller.set_state('GREEN')
                self._simple_state = 'GREEN'
                self.current_state = 'GREEN'
                logger.info("✅ LED set to GREEN")
                log_to_database('LED_CHANGE', 'GREEN - vehicles allowed', None, 0, 'GREEN', 'DETECTION')
    
    def _set_simple_red(self):
        """Set LED to RED in simple mode (called after yellow transition)"""
        with self._transition_lock:
            # Only set red if still in yellow state (vehicle might have appeared)
            if self._simple_state == 'YELLOW':
                self.led_controller.set_state('RED')
                self._simple_state = 'RED'
                self.current_state = 'RED'
                logger.info("🛑 LED set to RED")
                log_to_database('LED_CHANGE', 'RED - stop', None, 0, 'RED', 'AUTO')
    
    def request_pedestrian_crossing(self, direction):
        """
        Request pedestrian crossing for a direction
        
        Args:
            direction: 'NORTH', 'EAST', 'SOUTH', 'WEST'
            
        Returns:
            bool: True if request accepted, False if in cooldown
        """
        if direction not in self.DIRECTIONS:
            return False
        
        current_time = time.time()
        last_served = self.pedestrian_last_served[direction]
        
        # Check cooldown
        if current_time - last_served < self.T_PEDESTRIAN_COOLDOWN:
            remaining = int(self.T_PEDESTRIAN_COOLDOWN - (current_time - last_served))
            logger.info(f"Pedestrian request for {direction} in cooldown ({remaining}s remaining)")
            return False
        
        with self.lock:
            self.pedestrian_requests[direction] = True
        
        self._log_event("PEDESTRIAN", f"Crossing requested for {direction}")
        logger.info(f"Pedestrian crossing requested: {direction}")
        return True
    
    def set_mode(self, mode):
        """
        Set control mode
        
        Args:
            mode: 'SIMPLE', 'AUTO', or 'MANUAL'
            - SIMPLE: Immediate response to detection (default)
            - AUTO: Intelligent cycling with dynamic timing
            - MANUAL: Direct API control
        """
        mode = mode.upper()
        if mode not in ['SIMPLE', 'AUTO', 'MANUAL']:
            logger.warning(f"Invalid mode: {mode}")
            return False
        
        with self.lock:
            old_mode = self.mode
            self.mode = mode
            
            # Initialize simple mode state when switching to SIMPLE
            if mode == 'SIMPLE' and old_mode != 'SIMPLE':
                self._simple_state = 'RED'
                self.led_controller.set_state('RED')
        
        self._log_event("SYSTEM", f"Mode changed to {mode}")
        logger.info(f"Control mode set to: {mode}")
        log_to_database('SYSTEM', f"Mode changed from {old_mode} to {mode}", triggered_by='MANUAL')
        return True
    
    def manual_set_direction(self, direction, state):
        """
        Manually set a direction's light state (MANUAL mode only)
        
        Args:
            direction: Direction name or index
            state: 'RED', 'YELLOW', 'GREEN', 'RED_YELLOW'
        """
        if self.mode != 'MANUAL':
            logger.warning("Manual control only available in MANUAL mode")
            return False
        
        if isinstance(direction, str):
            if direction not in self.DIRECTIONS:
                return False
            direction_idx = self.DIRECTIONS.index(direction)
        else:
            direction_idx = direction
        
        self.led_controller.set_direction_state(direction_idx, state)
        self._log_event("MANUAL", f"{self.DIRECTIONS[direction_idx]} set to {state}")
        return True
    
    def _is_peak_hour(self):
        """Check if current time is peak hour"""
        current_time = datetime.now().time()
        
        # Morning peak: 7:00 - 9:00
        morning_peak = dt_time(7, 0) <= current_time <= dt_time(9, 0)
        
        # Evening peak: 17:00 - 19:00
        evening_peak = dt_time(17, 0) <= current_time <= dt_time(19, 0)
        
        return morning_peak or evening_peak
    
    def _is_night_mode(self):
        """Check if current time is night (low traffic expected)"""
        current_time = datetime.now().time()
        
        # Night: 22:00 - 6:00
        return current_time >= dt_time(22, 0) or current_time <= dt_time(6, 0)
    
    def _calculate_green_time(self, direction_idx):
        """
        Calculate optimal green time for a direction based on vehicle density
        
        Args:
            direction_idx: Direction index (0-3)
            
        Returns:
            float: Green time in seconds
        """
        direction = self.DIRECTIONS[direction_idx]
        vehicle_count = self.vehicle_counts[direction]
        
        # Get max vehicle count across all directions
        max_count = max(self.vehicle_counts.values())
        
        if max_count == 0:
            # No vehicles detected, use minimum time
            return self.T_MIN
        
        # Dynamic allocation based on density
        # T_green = T_min + (N_vehicles / N_max) * (T_max - T_min)
        ratio = vehicle_count / max_count
        green_time = self.T_MIN + ratio * (self.T_MAX - self.T_MIN)
        
        # Apply peak hour multiplier
        if self._is_peak_hour():
            green_time *= 1.2
        
        # Apply night mode reduction
        if self._is_night_mode() and vehicle_count < 2:
            green_time = max(self.T_MIN / 2, 5)  # Minimum 5 seconds
        
        # Anti-starvation: If direction has been waiting >3 cycles, boost time
        if self.waiting_cycles[direction] > 3:
            green_time = min(green_time * 1.5, self.T_MAX)
            logger.info(f"{direction} has been waiting {self.waiting_cycles[direction]} cycles - boosting green time")
        
        return green_time
    
    def _select_next_direction(self):
        """
        Select next direction for green light using priority queue
        
        Returns:
            int: Direction index
        """
        # Check for high-priority pedestrian requests
        for idx, direction in enumerate(self.DIRECTIONS):
            if self.pedestrian_requests[direction]:
                logger.info(f"Prioritizing {direction} for pedestrian crossing")
                return idx
        
        # Calculate priority for each direction
        priorities = []
        
        for idx, direction in enumerate(self.DIRECTIONS):
            vehicle_count = self.vehicle_counts[direction]
            waiting_cycles = self.waiting_cycles[direction]
            
            # Priority = vehicle_count + (waiting_cycles * 5)
            # Heavily weight waiting time to prevent starvation
            priority = vehicle_count + (waiting_cycles * 5)
            
            priorities.append((priority, idx))
        
        # Sort by priority (descending)
        priorities.sort(reverse=True, key=lambda x: x[0])
        
        # Select highest priority
        selected_idx = priorities[0][1]
        
        logger.info(f"Selected {self.DIRECTIONS[selected_idx]} (priority: {priorities[0][0]})")
        return selected_idx
    
    def _execute_transition(self, from_direction, to_direction):
        """
        Execute traffic light transition between directions
        
        Args:
            from_direction: Current green direction index
            to_direction: Next green direction index
        """
        # Step 1: Current green → Yellow
        logger.info(f"Transitioning: {self.DIRECTIONS[from_direction]} GREEN → YELLOW")
        self.led_controller.set_direction_state(from_direction, 'YELLOW')
        time.sleep(self.T_YELLOW)
        
        # Step 2: Current yellow → Red
        logger.info(f"{self.DIRECTIONS[from_direction]} YELLOW → RED")
        self.led_controller.set_direction_state(from_direction, 'RED')
        time.sleep(0.5)  # Brief all-red for safety
        
        # Step 3: Next red → Red+Yellow
        logger.info(f"{self.DIRECTIONS[to_direction]} RED → RED+YELLOW")
        self.led_controller.set_direction_state(to_direction, 'RED_YELLOW')
        time.sleep(self.T_RED_YELLOW)
        
        # Step 4: Next red+yellow → Green
        logger.info(f"{self.DIRECTIONS[to_direction]} RED+YELLOW → GREEN")
        self.led_controller.set_direction_state(to_direction, 'GREEN')
        
        self._log_event("TRANSITION", f"{self.DIRECTIONS[from_direction]} → {self.DIRECTIONS[to_direction]}")
    
    def _serve_pedestrian(self, direction_idx):
        """
        Serve pedestrian crossing request
        
        Args:
            direction_idx: Direction index
        """
        direction = self.DIRECTIONS[direction_idx]
        
        logger.info(f"Serving pedestrian crossing for {direction}")
        self._log_event("PEDESTRIAN", f"Crossing started for {direction}")
        
        # Green for pedestrians
        time.sleep(self.T_PEDESTRIAN)
        
        # Update tracking
        with self.lock:
            self.pedestrian_requests[direction] = False
            self.pedestrian_last_served[direction] = time.time()
        
        self.stats['pedestrian_requests_served'] += 1
        self._log_event("PEDESTRIAN", f"Crossing completed for {direction}")
    
    def _control_loop(self):
        """Main traffic control loop"""
        logger.info("Control loop started")
        
        # Initialize: All red
        self.led_controller.set_state('RED')
        self._simple_state = 'RED'
        self.current_state = 'RED'
        logger.info("All LEDs set to RED initially")
        time.sleep(1)
        
        while self.running:
            # In SIMPLE mode, LED control is handled directly by update_vehicle_counts
            if self.mode == 'SIMPLE':
                time.sleep(0.1)  # Just keep the thread alive
                continue
                
            if self.mode == 'MANUAL':
                logger.debug("Mode is MANUAL, waiting...")
                time.sleep(1)
                continue
            
            # AUTO mode: Intelligent cycling
            try:
                # Start with first direction green
                if self.current_state == 'RED':
                    self.current_direction = 0
                    self.led_controller.set_state('GREEN')
                    self.current_state = 'GREEN'
                    logger.info(f"Setting {self.DIRECTIONS[self.current_direction]} to GREEN")
                
                # Calculate green time for current direction
                green_time = self._calculate_green_time(self.current_direction)
                
                logger.info(f"✅ {self.DIRECTIONS[self.current_direction]} GREEN for {green_time:.1f}s (vehicles: {self.vehicle_counts[self.DIRECTIONS[self.current_direction]]})")
                
                # Wait for green time
                start_time = time.time()
                while time.time() - start_time < green_time and self.mode == 'AUTO':
                    # Check for interrupts (pedestrian priority)
                    if any(self.pedestrian_requests.values()):
                        # Allow current direction to finish minimum time
                        if time.time() - start_time >= self.T_MIN:
                            logger.info("Interrupting for pedestrian request")
                            break
                    
                    time.sleep(0.5)
                
                if self.mode != 'AUTO':
                    continue
                
                # Update waiting cycles
                for idx, direction in enumerate(self.DIRECTIONS):
                    if idx == self.current_direction:
                        self.waiting_cycles[direction] = 0
                    else:
                        self.waiting_cycles[direction] += 1
                
                # Select next direction
                next_direction = self._select_next_direction()
                
                # Handle pedestrian request
                if self.pedestrian_requests[self.DIRECTIONS[next_direction]]:
                    self._serve_pedestrian(next_direction)
                
                # Execute transition
                if next_direction != self.current_direction:
                    self._execute_transition(self.current_direction, next_direction)
                
                self.current_direction = next_direction
                self.stats['cycle_count'] += 1
                
            except Exception as e:
                logger.error(f"Error in control loop: {e}", exc_info=True)
                time.sleep(1)
        
        logger.info("Control loop stopped")
    
    def _log_event(self, event_type, message):
        """Log system event"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event = {
            'timestamp': timestamp,
            'type': event_type,
            'message': message
        }
        
        with self.lock:
            self.event_log.append(event)
    
    def get_status(self):
        """Get current system status"""
        with self.lock:
            # Get current LED state based on mode
            if self.mode == 'SIMPLE':
                current_led_state = self._simple_state
            else:
                current_led_state = self.current_state
            
            status = {
                'mode': self.mode,
                'current_state': current_led_state,
                'current_direction': self.DIRECTIONS[self.current_direction],
                'current_direction_idx': self.current_direction,
                'vehicle_counts': self.vehicle_counts.copy(),
                'total_vehicles': sum(self.vehicle_counts.values()),
                'waiting_cycles': self.waiting_cycles.copy(),
                'pedestrian_requests': self.pedestrian_requests.copy(),
                'led_states': self.led_controller.get_all_states(),
                'led_state': current_led_state,
                'statistics': self.stats.copy(),
                'is_peak_hour': self._is_peak_hour(),
                'is_night_mode': self._is_night_mode()
            }
        
        return status
    
    def get_event_log(self, limit=50):
        """
        Get recent event log
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of event dicts
        """
        with self.lock:
            return list(self.event_log)[-limit:]
    
    def emergency_stop(self):
        """Emergency stop - set all lights to red"""
        logger.warning("EMERGENCY STOP activated")
        self._log_event("EMERGENCY", "All lights set to RED")
        
        self.led_controller.set_all_red()
        
        with self.lock:
            self.mode = 'MANUAL'
