"""
Traffic Light Control Algorithm
Supports both SIMPLE mode (immediate response) and AUTO mode (intelligent cycling)
"""

import threading
import time
import logging
from collections import deque
from datetime import datetime, date, time as dt_time

logger = logging.getLogger(__name__)

# Track last vehicle count log time to avoid spam
_last_vehicle_count_log = 0
VEHICLE_COUNT_LOG_INTERVAL = 10  # Log every 10 seconds


def log_to_database(event_type, message, direction=None, vehicle_count=0, led_state=None, triggered_by='AUTO', direction_counts=None):
    """
    Log events to Django database
    Safe to call even when Django isn't fully loaded
    
    Args:
        event_type: Type of event (CAR, PEDESTRIAN, LED_CHANGE, SYSTEM, EMERGENCY)
        message: Event description
        direction: Direction (NORTH, EAST, SOUTH, WEST)
        vehicle_count: Total vehicle count
        led_state: LED state if changed
        triggered_by: What triggered the event
        direction_counts: Dict with counts per direction {'NORTH': 5, 'EAST': 3, ...}
    """
    try:
        from detection.models import DetectionEvent, TrafficLightState, VehicleCount, SystemStats
        
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
        
        # Log vehicle counts periodically (not every call)
        global _last_vehicle_count_log
        current_time = time.time()
        if direction_counts and (current_time - _last_vehicle_count_log) >= VEHICLE_COUNT_LOG_INTERVAL:
            _last_vehicle_count_log = current_time
            total = sum(direction_counts.values())
            VehicleCount.objects.create(
                north_count=direction_counts.get('NORTH', 0),
                east_count=direction_counts.get('EAST', 0),
                south_count=direction_counts.get('SOUTH', 0),
                west_count=direction_counts.get('WEST', 0),
                total_count=total
            )
            
            # Update daily stats
            today = date.today()
            stats, created = SystemStats.objects.get_or_create(date=today)
            stats.total_vehicles_detected += total
            if event_type == 'PEDESTRIAN':
                stats.total_pedestrian_requests += 1
            if led_state:
                stats.total_light_cycles += 1
            stats.save()
            
    except Exception as e:
        logger.debug(f"Could not log to database: {e}")


class TrafficController:
    """
    Traffic light controller with multiple modes
    
    Modes:
    - SIMPLE: Immediate response to vehicle detection (car → GREEN, no car → RED)
    - AUTO: Intelligent cycling with dynamic timing (green time proportional to vehicles)
    - MANUAL: Manual control through API
    
    INTELLIGENT ALGORITHM:
    - Green time = T_MIN + (vehicle_count * T_PER_VEHICLE), capped at T_MAX
    - Emergency vehicles get IMMEDIATE priority (instant green)
    - Pedestrians can request crossing (overrides after current cycle)
    
    LED Layout (8 LEDs configured as traffic light):
    - LEDs 0-2: RED section
    - LEDs 3-4: YELLOW section
    - LEDs 5-7: GREEN section
    """
    
    # Timing constants (seconds)
    T_MIN = 10   # Minimum green time for vehicles
    T_MAX = 60   # Maximum green time for vehicles
    T_PER_VEHICLE = 3  # Additional seconds per vehicle detected
    T_YELLOW = 2  # Yellow light duration
    T_RED_YELLOW = 1.5  # Red+Yellow transition
    
    # PEDESTRIAN TIMING - Pedestrians wait longer, cars get priority
    T_PEDESTRIAN = 12  # Pedestrian crossing green time (shorter)
    T_PEDESTRIAN_COOLDOWN = 45  # Longer cooldown between pedestrian requests
    T_PEDESTRIAN_MIN_WAIT = 20  # Minimum time pedestrians must wait before crossing
    T_PEDESTRIAN_MAX_WAIT = 120  # Maximum wait time before forcing pedestrian crossing
    
    # Car priority settings
    T_CAR_MIN_GREEN = 15  # Minimum green time for cars (longer)
    T_CAR_EXTENSION = 5  # Extend green if cars still coming
    T_CAR_WAITING_BONUS = 2  # Extra seconds per 10 seconds cars waited
    
    # Speed estimation (for calculating optimal timing)
    SPEED_ESTIMATION_ENABLED = True
    FRAMES_FOR_SPEED = 10  # Number of frames to estimate speed
    
    # Priority Lane Settings (e.g., bus lane)
    PRIORITY_LANE_ENABLED = False
    PRIORITY_LANE_DIRECTION = 'NORTH'  # Which direction is priority
    PRIORITY_LANE_MULTIPLIER = 1.5  # Priority lane gets 50% more green time
    PRIORITY_LANE_MIN_VEHICLES = 1  # Minimum vehicles to trigger priority
    
    # Traffic Balancing
    BALANCE_ENABLED = True
    MAX_WAIT_CYCLES = 3  # Max cycles a direction can wait before getting priority
    FAIRNESS_WEIGHT = 0.3  # Weight for fairness in scoring (0-1)
    
    # Simple mode settings
    SIMPLE_GREEN_DURATION = 5  # Seconds to show green after detection
    SIMPLE_YELLOW_DURATION = 2  # Seconds to show yellow before red
    
    # Emergency settings
    EMERGENCY_PRIORITY = False  # DISABLED by default (color detection needs tuning)
    EMERGENCY_GREEN_TIME = 20  # Green time for emergency vehicle
    
    # Directions
    DIRECTIONS = ['NORTH', 'EAST', 'SOUTH', 'WEST']
    
    def __init__(self, led_controller):
        """
        Initialize traffic controller
        
        Args:
            led_controller: LEDStripController instance
        """
        self.led_controller = led_controller
        
        # Emergency vehicle handling
        self.emergency_active = False
        self.emergency_direction = None
        
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
        
        # ============ INTELLIGENT TIMING TRACKING ============
        
        # Waiting time tracking (in seconds)
        self.car_waiting_time = {direction: 0 for direction in self.DIRECTIONS}
        self.car_waiting_start = {direction: 0 for direction in self.DIRECTIONS}
        self.waiting_cycles = {direction: 0 for direction in self.DIRECTIONS}
        
        # Pedestrian queue tracking
        self.pedestrian_count = {direction: 0 for direction in self.DIRECTIONS}
        self.pedestrian_waiting_start = {direction: 0 for direction in self.DIRECTIONS}
        self.pedestrian_waiting_time = {direction: 0 for direction in self.DIRECTIONS}
        
        # Speed estimation (vehicles per second entering zone)
        self.vehicle_speed_estimate = {direction: 0 for direction in self.DIRECTIONS}
        self.vehicle_history = {direction: deque(maxlen=self.FRAMES_FOR_SPEED) for direction in self.DIRECTIONS}
        
        # Priority lane tracking
        self.priority_lane_triggered = False
        self.last_priority_time = 0
        
        # Pedestrian requests
        self.pedestrian_requests = {direction: False for direction in self.DIRECTIONS}
        self.pedestrian_last_served = {direction: 0 for direction in self.DIRECTIONS}
        
        # Statistics
        self.stats = {
            'total_vehicles_processed': 0,
            'average_wait_time': 0,
            'green_time_efficiency': 0,
            'pedestrian_requests_served': 0,
            'pedestrian_requests_denied': 0,
            'cycle_count': 0,
            'priority_lane_activations': 0
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
    
    def handle_emergency(self, direction):
        """
        Handle emergency vehicle detection - IMMEDIATE priority
        
        Args:
            direction: Direction of emergency vehicle
        """
        if not self.EMERGENCY_PRIORITY:
            logger.debug(f"Emergency priority disabled - ignoring detection in {direction}")
            return
        
        # Use try-finally to prevent blocking
        try:
            with self.lock:
                if not self.emergency_active:
                    self.emergency_active = True
                    self.emergency_direction = direction
                    
                    logger.warning(f"🚨 EMERGENCY PRIORITY: {direction} - Switching to GREEN immediately!")
                    self._log_event("EMERGENCY", f"Emergency vehicle in {direction} - Priority activated")
                    
                    try:
                        log_to_database('EMERGENCY', f"Emergency vehicle priority for {direction}", direction, 0, 'GREEN', 'EMERGENCY')
                    except Exception as db_err:
                        logger.debug(f"Could not log to database: {db_err}")
                    
                    # Immediate transition to green for emergency
                    if self.led_controller:
                        self.led_controller.set_state('GREEN')
                    self.current_state = 'GREEN'
                    
                    # Schedule return to normal after emergency green time (non-blocking)
                    timer = threading.Timer(self.EMERGENCY_GREEN_TIME, self._end_emergency)
                    timer.daemon = True  # Don't block program exit
                    timer.start()
        except Exception as e:
            logger.error(f"Emergency handler error: {e}")
            self.emergency_active = False
    
    def _end_emergency(self):
        """End emergency priority mode"""
        with self.lock:
            self.emergency_active = False
            self.emergency_direction = None
            logger.info("🚨 Emergency priority ended - returning to normal operation")
            self._log_event("EMERGENCY", "Emergency priority ended")
    
    def calculate_green_time(self, vehicle_count):
        """
        INTELLIGENT ALGORITHM: Calculate green time proportional to vehicle count
        
        Formula: green_time = T_MIN + (vehicle_count * T_PER_VEHICLE)
        Capped between T_MIN and T_MAX
        
        Args:
            vehicle_count: Number of vehicles detected
            
        Returns:
            Green time in seconds
        """
        green_time = self.T_MIN + (vehicle_count * self.T_PER_VEHICLE)
        green_time = max(self.T_MIN, min(green_time, self.T_MAX))
        
        logger.debug(f"Calculated green time: {green_time}s for {vehicle_count} vehicles")
        return green_time
    
    def update_vehicle_counts(self, counts_dict, emergency_info=None):
        """
        Update vehicle counts from detection system
        In SIMPLE mode, triggers immediate LED response
        Handles emergency vehicle priority
        
        Args:
            counts_dict: Dict with keys 'NORTH', 'EAST', 'SOUTH', 'WEST'
            emergency_info: Dict with 'detected', 'direction' from detector
        """
        # Check for emergency vehicle FIRST (highest priority)
        if emergency_info and emergency_info.get('detected'):
            self.handle_emergency(emergency_info.get('direction'))
            return  # Emergency takes over, skip normal processing
        
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
            
            # Log vehicle counts to database periodically
            log_to_database(
                'CAR', 
                f"Vehicle count update: N={self.vehicle_counts['NORTH']} E={self.vehicle_counts['EAST']} S={self.vehicle_counts['SOUTH']} W={self.vehicle_counts['WEST']}", 
                direction=None, 
                vehicle_count=new_total,
                direction_counts=self.vehicle_counts.copy()
            )
        
        # Skip normal processing if emergency is active
        if self.emergency_active:
            return
        
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
    
    def update_waiting_times(self):
        """
        Update waiting times for all directions
        Called periodically to track how long cars/pedestrians have been waiting
        """
        current_time = time.time()
        
        for direction in self.DIRECTIONS:
            # Update car waiting time (if they're waiting at red)
            if self.vehicle_counts[direction] > 0:
                if self.car_waiting_start[direction] == 0:
                    # Start tracking wait time
                    self.car_waiting_start[direction] = current_time
                else:
                    # Update accumulated wait time
                    self.car_waiting_time[direction] = current_time - self.car_waiting_start[direction]
            
            # Update pedestrian waiting time
            if self.pedestrian_requests[direction]:
                if self.pedestrian_waiting_start[direction] == 0:
                    self.pedestrian_waiting_start[direction] = current_time
                else:
                    self.pedestrian_waiting_time[direction] = current_time - self.pedestrian_waiting_start[direction]
    
    def reset_waiting_time(self, direction):
        """Reset waiting time for a direction after it gets green"""
        self.car_waiting_time[direction] = 0
        self.car_waiting_start[direction] = 0
        self.waiting_cycles[direction] = 0
        
        if self.pedestrian_requests[direction]:
            self.pedestrian_waiting_time[direction] = 0
            self.pedestrian_waiting_start[direction] = 0
    
    def estimate_vehicle_speed(self, direction):
        """
        Estimate vehicle arrival speed (vehicles per second)
        Based on change in vehicle count over time
        
        Returns:
            float: Estimated vehicles per second (0 if no movement)
        """
        if not self.SPEED_ESTIMATION_ENABLED:
            return 0
        
        history = self.vehicle_history[direction]
        if len(history) < 2:
            return 0
        
        # Calculate rate of change
        first = history[0]
        last = history[-1]
        
        if last['count'] > first['count']:
            time_diff = last['time'] - first['time']
            if time_diff > 0:
                return (last['count'] - first['count']) / time_diff
        
        return 0
    
    def update_vehicle_history(self, direction, count):
        """Add vehicle count to history for speed estimation"""
        self.vehicle_history[direction].append({
            'time': time.time(),
            'count': count
        })
    
    def calculate_direction_priority_score(self, direction):
        """
        Calculate priority score for a direction
        
        INTELLIGENT SCORING ALGORITHM:
        - Base score: Number of vehicles waiting
        - Wait time bonus: +2 points per 10 seconds waiting
        - Cycle starvation: +10 points per cycle waiting (prevents starvation)
        - Speed factor: +5 if vehicles are actively arriving
        - Priority lane: x1.5 multiplier if direction is priority lane
        - Pedestrian penalty: -5 if pedestrians waiting (cars get priority)
        
        Returns:
            float: Priority score (higher = more urgent)
        """
        vehicle_count = self.vehicle_counts[direction]
        wait_time = self.car_waiting_time[direction]
        cycles_waiting = self.waiting_cycles[direction]
        speed = self.vehicle_speed_estimate[direction]
        
        # Base score from vehicle count
        score = vehicle_count * 10
        
        # Wait time bonus (cars that have been waiting longer get priority)
        wait_bonus = (wait_time / 10) * self.T_CAR_WAITING_BONUS
        score += wait_bonus
        
        # Anti-starvation: cycles waiting bonus
        starvation_bonus = cycles_waiting * 10
        score += starvation_bonus
        
        # Speed factor: if vehicles actively arriving, higher priority
        if speed > 0:
            score += 5 * min(speed, 2)  # Cap at 10 bonus points
        
        # Priority lane multiplier
        if self.PRIORITY_LANE_ENABLED and direction == self.PRIORITY_LANE_DIRECTION:
            if vehicle_count >= self.PRIORITY_LANE_MIN_VEHICLES:
                score *= self.PRIORITY_LANE_MULTIPLIER
                logger.debug(f"Priority lane {direction} activated (multiplier: {self.PRIORITY_LANE_MULTIPLIER})")
        
        # Pedestrian penalty (cars get priority over pedestrians)
        if self.pedestrian_requests.get(direction, False):
            pedestrian_wait = self.pedestrian_waiting_time.get(direction, 0)
            
            # Only give pedestrians priority if they've waited too long
            if pedestrian_wait >= self.T_PEDESTRIAN_MAX_WAIT:
                # Force pedestrian crossing if waited too long
                score = 0  # Reset car priority
                logger.info(f"Pedestrian in {direction} exceeded max wait ({pedestrian_wait:.0f}s) - forcing crossing")
            elif pedestrian_wait < self.T_PEDESTRIAN_MIN_WAIT:
                # Pedestrians haven't waited long enough, penalize
                score += 20  # Keep car priority high
        
        return score
    
    def _calculate_green_time(self, direction_idx):
        """
        Calculate optimal green time for a direction
        
        INTELLIGENT ALGORITHM:
        1. Base time from vehicle count
        2. Bonus for waiting time
        3. Extension if vehicles still arriving (speed > 0)
        4. Priority lane bonus
        5. Peak hour adjustment
        6. Fairness cap (don't starve other directions)
        
        Args:
            direction_idx: Direction index (0-3)
            
        Returns:
            float: Green time in seconds
        """
        direction = self.DIRECTIONS[direction_idx]
        vehicle_count = self.vehicle_counts[direction]
        wait_time = self.car_waiting_time[direction]
        speed = self.estimate_vehicle_speed(direction)
        
        # Base green time calculation
        # T_green = T_MIN + (vehicles * T_PER_VEHICLE)
        base_time = self.T_CAR_MIN_GREEN + (vehicle_count * self.T_PER_VEHICLE)
        
        # Wait time bonus: +2s per 10 seconds cars were waiting
        wait_bonus = (wait_time / 10) * self.T_CAR_WAITING_BONUS
        base_time += wait_bonus
        
        # Speed extension: if vehicles still arriving, extend
        if speed > 0.5:  # At least 0.5 vehicles per second arriving
            extension = self.T_CAR_EXTENSION * min(speed, 2)
            base_time += extension
            logger.debug(f"{direction}: Extending green by {extension:.1f}s (vehicles arriving)")
        
        # Priority lane bonus
        if self.PRIORITY_LANE_ENABLED and direction == self.PRIORITY_LANE_DIRECTION:
            base_time *= self.PRIORITY_LANE_MULTIPLIER
            self.stats['priority_lane_activations'] += 1
        
        # Peak hour adjustment
        if self._is_peak_hour():
            base_time *= 1.2
        
        # Night mode reduction
        if self._is_night_mode() and vehicle_count < 2:
            base_time = max(self.T_MIN / 2, 5)
        
        # Fairness cap: Check if other directions are starving
        if self.BALANCE_ENABLED:
            max_other_wait = 0
            for other_dir in self.DIRECTIONS:
                if other_dir != direction:
                    max_other_wait = max(max_other_wait, self.waiting_cycles[other_dir])
            
            # If another direction has been waiting too long, reduce our time
            if max_other_wait >= self.MAX_WAIT_CYCLES:
                reduction = 0.7  # Reduce to 70%
                base_time *= reduction
                logger.info(f"{direction}: Reducing green time (fairness - others waiting {max_other_wait} cycles)")
        
        # Clamp to min/max
        green_time = max(self.T_MIN, min(base_time, self.T_MAX))
        
        logger.debug(f"{direction}: Green time = {green_time:.1f}s (vehicles={vehicle_count}, wait={wait_time:.0f}s)")
        return green_time
    
    def _select_next_direction(self):
        """
        Select next direction for green light using intelligent priority scoring
        
        ALGORITHM:
        1. Update all waiting times
        2. Calculate priority score for each direction
        3. Check pedestrian requests (with minimum wait enforcement)
        4. Select highest priority direction
        5. Handle traffic balancing
        
        Returns:
            int: Direction index
        """
        # Update waiting times
        self.update_waiting_times()
        
        # Check for forced pedestrian crossing (waited too long)
        for idx, direction in enumerate(self.DIRECTIONS):
            if self.pedestrian_requests[direction]:
                wait_time = self.pedestrian_waiting_time[direction]
                if wait_time >= self.T_PEDESTRIAN_MAX_WAIT:
                    logger.info(f"FORCED: Pedestrian {direction} waited {wait_time:.0f}s (max: {self.T_PEDESTRIAN_MAX_WAIT}s)")
                    return idx
        
        # Calculate priority score for each direction
        scores = []
        
        for idx, direction in enumerate(self.DIRECTIONS):
            score = self.calculate_direction_priority_score(direction)
            scores.append((score, idx, direction))
            logger.debug(f"{direction}: Priority score = {score:.1f}")
        
        # Sort by score (descending)
        scores.sort(reverse=True, key=lambda x: x[0])
        
        # Select highest priority
        selected_score, selected_idx, selected_dir = scores[0]
        
        # Check if selection has any vehicles or pedestrians
        if self.vehicle_counts[selected_dir] == 0 and not self.pedestrian_requests[selected_dir]:
            # Try next best option
            for score, idx, direction in scores[1:]:
                if self.vehicle_counts[direction] > 0 or self.pedestrian_requests[direction]:
                    selected_idx = idx
                    selected_dir = direction
                    selected_score = score
                    break
        
        # Update waiting cycles for non-selected directions
        for idx, direction in enumerate(self.DIRECTIONS):
            if idx != selected_idx:
                if self.vehicle_counts[direction] > 0:
                    self.waiting_cycles[direction] += 1
        
        # Reset waiting for selected direction
        self.reset_waiting_time(selected_dir)
        
        logger.info(f"Selected {selected_dir} (score: {selected_score:.1f}, vehicles: {self.vehicle_counts[selected_dir]})")
        return selected_idx
    
    def handle_pedestrian_request_intelligent(self, direction):
        """
        Handle pedestrian crossing request with intelligent timing
        
        Rules:
        1. Pedestrians must wait minimum time (T_PEDESTRIAN_MIN_WAIT)
        2. Cars get priority during that time
        3. After max wait, pedestrians are forced through
        4. Track pedestrian count for reporting
        
        Returns:
            dict: Status of request
        """
        if direction not in self.DIRECTIONS:
            return {'success': False, 'message': 'Invalid direction'}
        
        current_time = time.time()
        last_served = self.pedestrian_last_served.get(direction, 0)
        
        # Check cooldown
        if current_time - last_served < self.T_PEDESTRIAN_COOLDOWN:
            remaining = int(self.T_PEDESTRIAN_COOLDOWN - (current_time - last_served))
            self.stats['pedestrian_requests_denied'] += 1
            return {
                'success': False,
                'message': f'Cooldown active ({remaining}s remaining)',
                'wait_required': True
            }
        
        # Register the request
        with self.lock:
            self.pedestrian_requests[direction] = True
            self.pedestrian_count[direction] = self.pedestrian_count.get(direction, 0) + 1
            
            if self.pedestrian_waiting_start[direction] == 0:
                self.pedestrian_waiting_start[direction] = current_time
        
        # Calculate estimated wait time
        car_count = sum(self.vehicle_counts.values())
        
        if car_count > 0:
            estimated_wait = max(self.T_PEDESTRIAN_MIN_WAIT, car_count * 3)
            estimated_wait = min(estimated_wait, self.T_PEDESTRIAN_MAX_WAIT)
        else:
            estimated_wait = 5  # Quick crossing if no cars
        
        self._log_event("PEDESTRIAN", f"Crossing requested for {direction} (est. wait: {estimated_wait}s)")
        logger.info(f"Pedestrian request: {direction} (cars waiting: {car_count}, est. wait: {estimated_wait}s)")
        
        return {
            'success': True,
            'message': f'Request registered. Estimated wait: {estimated_wait}s',
            'estimated_wait': estimated_wait,
            'cars_ahead': car_count
        }
    
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
    
    def get_algorithm_settings(self):
        """
        Get all algorithm settings for display/configuration
        
        Returns:
            dict: All configurable settings
        """
        return {
            'timing': {
                'T_MIN': self.T_MIN,
                'T_MAX': self.T_MAX,
                'T_PER_VEHICLE': self.T_PER_VEHICLE,
                'T_YELLOW': self.T_YELLOW,
                'T_RED_YELLOW': self.T_RED_YELLOW,
            },
            'pedestrian': {
                'T_PEDESTRIAN': self.T_PEDESTRIAN,
                'T_PEDESTRIAN_COOLDOWN': self.T_PEDESTRIAN_COOLDOWN,
                'T_PEDESTRIAN_MIN_WAIT': self.T_PEDESTRIAN_MIN_WAIT,
                'T_PEDESTRIAN_MAX_WAIT': self.T_PEDESTRIAN_MAX_WAIT,
            },
            'car_priority': {
                'T_CAR_MIN_GREEN': self.T_CAR_MIN_GREEN,
                'T_CAR_EXTENSION': self.T_CAR_EXTENSION,
                'T_CAR_WAITING_BONUS': self.T_CAR_WAITING_BONUS,
            },
            'priority_lane': {
                'enabled': self.PRIORITY_LANE_ENABLED,
                'direction': self.PRIORITY_LANE_DIRECTION,
                'multiplier': self.PRIORITY_LANE_MULTIPLIER,
                'min_vehicles': self.PRIORITY_LANE_MIN_VEHICLES,
            },
            'balancing': {
                'enabled': self.BALANCE_ENABLED,
                'max_wait_cycles': self.MAX_WAIT_CYCLES,
                'fairness_weight': self.FAIRNESS_WEIGHT,
            },
            'simple_mode': {
                'green_duration': self.SIMPLE_GREEN_DURATION,
                'yellow_duration': self.SIMPLE_YELLOW_DURATION,
            },
            'speed_estimation': {
                'enabled': self.SPEED_ESTIMATION_ENABLED,
                'frames_for_speed': self.FRAMES_FOR_SPEED,
            }
        }
    
    def update_algorithm_settings(self, settings):
        """
        Update algorithm settings
        
        Args:
            settings: Dict with settings to update
            
        Returns:
            dict: Updated settings
        """
        updated = []
        
        # Timing settings
        if 'timing' in settings:
            t = settings['timing']
            if 'T_MIN' in t:
                self.T_MIN = max(5, min(30, int(t['T_MIN'])))
                updated.append('T_MIN')
            if 'T_MAX' in t:
                self.T_MAX = max(30, min(120, int(t['T_MAX'])))
                updated.append('T_MAX')
            if 'T_PER_VEHICLE' in t:
                self.T_PER_VEHICLE = max(1, min(10, int(t['T_PER_VEHICLE'])))
                updated.append('T_PER_VEHICLE')
        
        # Pedestrian settings
        if 'pedestrian' in settings:
            p = settings['pedestrian']
            if 'T_PEDESTRIAN' in p:
                self.T_PEDESTRIAN = max(5, min(30, int(p['T_PEDESTRIAN'])))
                updated.append('T_PEDESTRIAN')
            if 'T_PEDESTRIAN_COOLDOWN' in p:
                self.T_PEDESTRIAN_COOLDOWN = max(10, min(120, int(p['T_PEDESTRIAN_COOLDOWN'])))
                updated.append('T_PEDESTRIAN_COOLDOWN')
            if 'T_PEDESTRIAN_MIN_WAIT' in p:
                self.T_PEDESTRIAN_MIN_WAIT = max(5, min(60, int(p['T_PEDESTRIAN_MIN_WAIT'])))
                updated.append('T_PEDESTRIAN_MIN_WAIT')
            if 'T_PEDESTRIAN_MAX_WAIT' in p:
                self.T_PEDESTRIAN_MAX_WAIT = max(30, min(300, int(p['T_PEDESTRIAN_MAX_WAIT'])))
                updated.append('T_PEDESTRIAN_MAX_WAIT')
        
        # Car priority settings
        if 'car_priority' in settings:
            c = settings['car_priority']
            if 'T_CAR_MIN_GREEN' in c:
                self.T_CAR_MIN_GREEN = max(5, min(30, int(c['T_CAR_MIN_GREEN'])))
                updated.append('T_CAR_MIN_GREEN')
            if 'T_CAR_EXTENSION' in c:
                self.T_CAR_EXTENSION = max(1, min(15, int(c['T_CAR_EXTENSION'])))
                updated.append('T_CAR_EXTENSION')
            if 'T_CAR_WAITING_BONUS' in c:
                self.T_CAR_WAITING_BONUS = max(0, min(10, int(c['T_CAR_WAITING_BONUS'])))
                updated.append('T_CAR_WAITING_BONUS')
        
        # Priority lane settings
        if 'priority_lane' in settings:
            pl = settings['priority_lane']
            if 'enabled' in pl:
                self.PRIORITY_LANE_ENABLED = bool(pl['enabled'])
                updated.append('PRIORITY_LANE_ENABLED')
            if 'direction' in pl and pl['direction'] in self.DIRECTIONS:
                self.PRIORITY_LANE_DIRECTION = pl['direction']
                updated.append('PRIORITY_LANE_DIRECTION')
            if 'multiplier' in pl:
                self.PRIORITY_LANE_MULTIPLIER = max(1.0, min(3.0, float(pl['multiplier'])))
                updated.append('PRIORITY_LANE_MULTIPLIER')
            if 'min_vehicles' in pl:
                self.PRIORITY_LANE_MIN_VEHICLES = max(1, min(10, int(pl['min_vehicles'])))
                updated.append('PRIORITY_LANE_MIN_VEHICLES')
        
        # Balancing settings
        if 'balancing' in settings:
            b = settings['balancing']
            if 'enabled' in b:
                self.BALANCE_ENABLED = bool(b['enabled'])
                updated.append('BALANCE_ENABLED')
            if 'max_wait_cycles' in b:
                self.MAX_WAIT_CYCLES = max(1, min(10, int(b['max_wait_cycles'])))
                updated.append('MAX_WAIT_CYCLES')
        
        logger.info(f"Algorithm settings updated: {updated}")
        self._log_event("SYSTEM", f"Algorithm settings updated: {', '.join(updated)}")
        
        return {
            'success': True,
            'updated': updated,
            'settings': self.get_algorithm_settings()
        }
    
    def get_detailed_status(self):
        """
        Get detailed status including waiting times, scores, and predictions
        
        Returns:
            dict: Comprehensive status
        """
        # Update waiting times first
        self.update_waiting_times()
        
        # Calculate scores for each direction
        direction_details = {}
        for direction in self.DIRECTIONS:
            score = self.calculate_direction_priority_score(direction)
            speed = self.estimate_vehicle_speed(direction)
            
            direction_details[direction] = {
                'vehicles': self.vehicle_counts[direction],
                'waiting_time_seconds': self.car_waiting_time[direction],
                'waiting_cycles': self.waiting_cycles[direction],
                'priority_score': round(score, 1),
                'vehicle_speed': round(speed, 2),
                'pedestrian_request': self.pedestrian_requests[direction],
                'pedestrian_waiting': self.pedestrian_waiting_time.get(direction, 0)
            }
        
        return {
            'mode': self.mode,
            'current_state': self.current_state,
            'current_direction': self.DIRECTIONS[self.current_direction],
            'directions': direction_details,
            'total_vehicles': sum(self.vehicle_counts.values()),
            'settings': {
                'priority_lane_enabled': self.PRIORITY_LANE_ENABLED,
                'priority_lane_direction': self.PRIORITY_LANE_DIRECTION,
                'balance_enabled': self.BALANCE_ENABLED,
                'pedestrian_min_wait': self.T_PEDESTRIAN_MIN_WAIT,
                'pedestrian_max_wait': self.T_PEDESTRIAN_MAX_WAIT,
            },
            'statistics': self.stats.copy(),
            'is_peak_hour': self._is_peak_hour(),
            'is_night_mode': self._is_night_mode()
        }
