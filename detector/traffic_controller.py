"""
Intelligent Traffic Light Control Algorithm
Implements dynamic timing, fair scheduling, and pedestrian priority
"""

import threading
import time
import logging
from collections import deque
from datetime import datetime, time as dt_time

logger = logging.getLogger(__name__)


class TrafficController:
    """
    Intelligent traffic light controller with adaptive timing
    
    Features:
    - Dynamic green time allocation based on vehicle density
    - Fair scheduling with anti-starvation
    - Pedestrian priority with gesture detection
    - Peak hour adaptation
    - Night mode for low traffic
    """
    
    # Timing constants (seconds)
    T_MIN = 10   # Minimum green time
    T_MAX = 60   # Maximum green time
    T_YELLOW = 2  # Yellow light duration
    T_RED_YELLOW = 1.5  # Red+Yellow transition
    T_PEDESTRIAN = 15  # Pedestrian green time
    T_PEDESTRIAN_COOLDOWN = 30  # Cooldown between pedestrian requests
    
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
        self.mode = 'AUTO'  # AUTO or MANUAL
        self.running = False
        
        # Vehicle counts per direction
        self.vehicle_counts = {direction: 0 for direction in self.DIRECTIONS}
        
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
        
        Args:
            counts_dict: Dict with keys 'NORTH', 'EAST', 'SOUTH', 'WEST'
        """
        with self.lock:
            for direction in self.DIRECTIONS:
                if direction in counts_dict:
                    self.vehicle_counts[direction] = counts_dict[direction]
    
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
            mode: 'AUTO' or 'MANUAL'
        """
        if mode not in ['AUTO', 'MANUAL']:
            logger.warning(f"Invalid mode: {mode}")
            return False
        
        with self.lock:
            self.mode = mode
        
        self._log_event("SYSTEM", f"Mode changed to {mode}")
        logger.info(f"Control mode set to: {mode}")
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
        self.led_controller.set_all_red()
        time.sleep(2)
        
        # Start with first direction
        self.current_direction = 0
        self.led_controller.set_direction_state(self.current_direction, 'GREEN')
        
        while self.running:
            if self.mode != 'AUTO':
                time.sleep(1)
                continue
            
            try:
                # Calculate green time for current direction
                green_time = self._calculate_green_time(self.current_direction)
                
                logger.info(f"{self.DIRECTIONS[self.current_direction]} green for {green_time:.1f}s")
                
                # Wait for green time
                start_time = time.time()
                while time.time() - start_time < green_time:
                    # Check for interrupts (pedestrian priority)
                    if any(self.pedestrian_requests.values()):
                        # Allow current direction to finish minimum time
                        if time.time() - start_time >= self.T_MIN:
                            logger.info("Interrupting for pedestrian request")
                            break
                    
                    time.sleep(0.5)
                
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
            status = {
                'mode': self.mode,
                'current_direction': self.DIRECTIONS[self.current_direction],
                'current_direction_idx': self.current_direction,
                'vehicle_counts': self.vehicle_counts.copy(),
                'waiting_cycles': self.waiting_cycles.copy(),
                'pedestrian_requests': self.pedestrian_requests.copy(),
                'led_states': self.led_controller.get_all_states(),
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
