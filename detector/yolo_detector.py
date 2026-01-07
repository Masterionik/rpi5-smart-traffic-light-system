import threading
import logging
from ultralytics import YOLO
import cv2
import numpy as np
from collections import defaultdict, deque
import time

logger = logging.getLogger(__name__)


class VehicleTracker:
    """
    Simple vehicle tracking using centroid tracking
    Assigns unique IDs to vehicles and tracks them across frames
    """
    def __init__(self, max_disappeared=30):
        self.next_id = 0
        self.objects = {}  # ID -> centroid
        self.disappeared = {}  # ID -> frames disappeared
        self.max_disappeared = max_disappeared
        self.vehicle_count_history = deque(maxlen=100)  # Last 100 frame counts
        
    def register(self, centroid):
        """Register a new object with unique ID"""
        self.objects[self.next_id] = centroid
        self.disappeared[self.next_id] = 0
        self.next_id += 1
        return self.next_id - 1
    
    def deregister(self, object_id):
        """Remove object from tracking"""
        del self.objects[object_id]
        del self.disappeared[object_id]
    
    def update(self, detections):
        """
        Update tracked objects with new detections
        
        Args:
            detections: List of (centroid_x, centroid_y, bbox) tuples
            
        Returns:
            Dict of {object_id: (centroid, bbox)}
        """
        # If no detections, mark all as disappeared
        if len(detections) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            
            return {}
        
        # If no existing objects, register all as new
        if len(self.objects) == 0:
            result = {}
            for detection in detections:
                centroid, bbox = detection
                obj_id = self.register(centroid)
                result[obj_id] = (centroid, bbox)
            return result
        
        # Match existing objects to new detections
        object_ids = list(self.objects.keys())
        object_centroids = list(self.objects.values())
        
        detection_centroids = [d[0] for d in detections]
        
        # Compute distance matrix
        distances = np.zeros((len(object_centroids), len(detection_centroids)))
        for i, obj_centroid in enumerate(object_centroids):
            for j, det_centroid in enumerate(detection_centroids):
                distances[i, j] = np.linalg.norm(
                    np.array(obj_centroid) - np.array(det_centroid)
                )
        
        # Match using minimum distance
        rows = distances.min(axis=1).argsort()
        cols = distances.argmin(axis=1)[rows]
        
        used_rows = set()
        used_cols = set()
        result = {}
        
        for row, col in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue
            
            # If distance is reasonable, match them
            if distances[row, col] < 50:  # pixels
                object_id = object_ids[row]
                self.objects[object_id] = detection_centroids[col]
                self.disappeared[object_id] = 0
                result[object_id] = (detection_centroids[col], detections[col][1])
                
                used_rows.add(row)
                used_cols.add(col)
        
        # Handle unmatched objects (disappeared)
        unused_rows = set(range(len(object_centroids))) - used_rows
        for row in unused_rows:
            object_id = object_ids[row]
            self.disappeared[object_id] += 1
            
            if self.disappeared[object_id] > self.max_disappeared:
                self.deregister(object_id)
        
        # Register new detections
        unused_cols = set(range(len(detections))) - used_cols
        for col in unused_cols:
            centroid, bbox = detections[col]
            obj_id = self.register(centroid)
            result[obj_id] = (centroid, bbox)
        
        return result


class YOLODetector:
    """
    Enhanced YOLO vehicle detection with tracking and ROI support
    Optimized for Raspberry Pi 5 with multiple vehicle classes
    Includes EMERGENCY VEHICLE detection for priority handling
    """
    
    # COCO dataset vehicle classes
    VEHICLE_CLASSES = {
        2: 'car',
        3: 'motorcycle', 
        5: 'bus',
        7: 'truck'
    }
    
    # Emergency vehicle detection (visual cues)
    # We detect based on color patterns typical of emergency vehicles
    EMERGENCY_COLORS = {
        'ambulance': [(255, 0, 0), (255, 255, 255)],  # Red and white
        'police': [(0, 0, 255), (255, 255, 255)],      # Blue and white
        'fire': [(255, 0, 0), (255, 255, 0)]           # Red and yellow
    }
    
    def __init__(self, model_name='yolov8n.pt'):
        """
        Initialize YOLO detector with tracking
        
        Args:
            model_name: YOLO model ('yolov8n.pt' for nano - fastest on RPi5)
        """
        self.model = None
        self.model_name = model_name
        self.lock = threading.Lock()
        self.is_loaded = False
        
        # Tracking
        self.tracker = VehicleTracker(max_disappeared=30)
        
        # Detection statistics per direction
        self.direction_counts = {
            'NORTH': 0,
            'EAST': 0,
            'SOUTH': 0,
            'WEST': 0
        }
        
        # ROI (Region of Interest) for each direction
        # Format: (x1, y1, x2, y2) in normalized coordinates [0, 1]
        self.roi_zones = {
            'NORTH': (0.0, 0.0, 0.5, 0.5),    # Top-left quadrant
            'EAST': (0.5, 0.0, 1.0, 0.5),     # Top-right quadrant
            'SOUTH': (0.5, 0.5, 1.0, 1.0),    # Bottom-right quadrant
            'WEST': (0.0, 0.5, 0.5, 1.0)      # Bottom-left quadrant
        }
        
        # Performance metrics
        self.fps = 0
        self.last_time = time.time()
        self.frame_count = 0
        
        # Detection confidence threshold
        self.confidence_threshold = 0.5
        
        # Emergency vehicle detection
        self.emergency_detected = False
        self.emergency_direction = None
        self.emergency_cooldown = 0  # Frames since last emergency
        
    def load_model(self):
        """Load YOLO model"""
        try:
            logger.info(f"Loading YOLO model: {self.model_name}")
            self.model = YOLO(self.model_name)
            self.is_loaded = True
            logger.info("YOLO model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.is_loaded = False
            return False
    
    def set_roi(self, direction, x1, y1, x2, y2):
        """
        Set ROI for a specific direction
        
        Args:
            direction: 'NORTH', 'EAST', 'SOUTH', 'WEST'
            x1, y1, x2, y2: Normalized coordinates [0, 1]
        """
        if direction in self.roi_zones:
            self.roi_zones[direction] = (x1, y1, x2, y2)
            logger.info(f"ROI set for {direction}: {self.roi_zones[direction]}")
    
    def _is_in_roi(self, centroid, frame_shape, direction):
        """Check if centroid is within ROI for a direction"""
        h, w = frame_shape[:2]
        cx, cy = centroid
        
        # Normalize centroid
        cx_norm = cx / w
        cy_norm = cy / h
        
        x1, y1, x2, y2 = self.roi_zones[direction]
        
        return x1 <= cx_norm <= x2 and y1 <= cy_norm <= y2
    
    def _calculate_centroid(self, bbox):
        """Calculate centroid from bounding box"""
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return (cx, cy)
    
    def _detect_emergency_vehicle(self, frame, bbox):
        """
        Detect if a vehicle is an emergency vehicle based on color patterns.
        Looks for red/blue flashing light colors typical of emergency vehicles.
        
        Args:
            frame: Input frame (BGR)
            bbox: Bounding box (x1, y1, x2, y2)
            
        Returns:
            Tuple of (is_emergency, emergency_type)
        """
        try:
            x1, y1, x2, y2 = map(int, bbox)
            
            # Get vehicle region
            vehicle_roi = frame[y1:y2, x1:x2]
            if vehicle_roi.size == 0:
                return False, None
            
            # Convert to HSV for better color detection
            hsv = cv2.cvtColor(vehicle_roi, cv2.COLOR_BGR2HSV)
            
            # Define color ranges for emergency lights
            # Red color range (emergency lights)
            red_lower1 = np.array([0, 100, 100])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([160, 100, 100])
            red_upper2 = np.array([180, 255, 255])
            
            # Blue color range (police lights)
            blue_lower = np.array([100, 100, 100])
            blue_upper = np.array([130, 255, 255])
            
            # Create masks
            red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
            red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
            red_mask = red_mask1 | red_mask2
            blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
            
            # Calculate percentage of emergency colors
            total_pixels = vehicle_roi.shape[0] * vehicle_roi.shape[1]
            red_pixels = cv2.countNonZero(red_mask)
            blue_pixels = cv2.countNonZero(blue_mask)
            
            red_ratio = red_pixels / total_pixels if total_pixels > 0 else 0
            blue_ratio = blue_pixels / total_pixels if total_pixels > 0 else 0
            
            # STRICT thresholds to avoid false positives
            # Emergency lights typically occupy a significant portion of vehicle top area
            # Threshold: 15% of vehicle must be emergency color + minimum 500 pixels
            EMERGENCY_THRESHOLD = 0.15  # 15% threshold (was 5%, too sensitive)
            MIN_EMERGENCY_PIXELS = 500  # Minimum pixels to trigger
            
            # Both red AND blue must be present for police (reduces false positives)
            if (red_ratio > EMERGENCY_THRESHOLD and blue_ratio > EMERGENCY_THRESHOLD and 
                red_pixels > MIN_EMERGENCY_PIXELS and blue_pixels > MIN_EMERGENCY_PIXELS):
                logger.info(f"Emergency detected: red={red_ratio:.2%}, blue={blue_ratio:.2%}")
                return True, 'police'  # Red + Blue = Police
            
            # Very high threshold for single color (30% to avoid taillights, etc.)
            elif red_ratio > 0.30 and red_pixels > MIN_EMERGENCY_PIXELS * 2:
                logger.info(f"Emergency ambulance detected: red={red_ratio:.2%}")
                return True, 'ambulance'  # Strong red = Ambulance/Fire
            
            return False, None
            
        except Exception as e:
            logger.debug(f"Emergency detection error: {e}")
            return False, None
    
    def detect_vehicles(self, frame, draw_roi=True):
        """
        Detect and track vehicles in frame with ROI support
        
        Args:
            frame: Input frame (BGR)
            draw_roi: Whether to draw ROI zones on frame
            
        Returns:
            Tuple of (annotated_frame, direction_counts_dict, tracked_objects)
        """
        if not self.is_loaded or self.model is None:
            return frame, self.direction_counts, {}
        
        try:
            # Run YOLO inference
            results = self.model(frame, verbose=False, conf=self.confidence_threshold)
            
            # Reset direction counts
            for direction in self.direction_counts:
                self.direction_counts[direction] = 0
            
            annotated_frame = frame.copy()
            h, w = frame.shape[:2]
            
            # Draw ROI zones if requested
            if draw_roi:
                colors = {
                    'NORTH': (255, 0, 0),    # Blue
                    'EAST': (0, 255, 0),     # Green
                    'SOUTH': (0, 0, 255),    # Red
                    'WEST': (255, 255, 0)    # Cyan
                }
                
                for direction, (x1, y1, x2, y2) in self.roi_zones.items():
                    pt1 = (int(x1 * w), int(y1 * h))
                    pt2 = (int(x2 * w), int(y2 * h))
                    cv2.rectangle(annotated_frame, pt1, pt2, colors[direction], 2)
                    
                    # Add label
                    label_pos = (pt1[0] + 5, pt1[1] + 20)
                    cv2.putText(
                        annotated_frame,
                        direction,
                        label_pos,
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        colors[direction],
                        2
                    )
            
            # Process detections
            detections = []
            
            if results and len(results) > 0:
                result = results[0]
                
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    # Filter for vehicle classes
                    if class_id in self.VEHICLE_CLASSES:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        bbox = (x1, y1, x2, y2)
                        centroid = self._calculate_centroid(bbox)
                        
                        detections.append((centroid, bbox))
            
            # Update tracker
            tracked_objects = self.tracker.update(detections)
            
            # Reset emergency status
            self.emergency_detected = False
            self.emergency_direction = None
            self.emergency_cooldown += 1
            
            # Count vehicles per direction and draw annotations
            for obj_id, (centroid, bbox) in tracked_objects.items():
                x1, y1, x2, y2 = bbox
                
                # Check for emergency vehicle
                is_emergency, emergency_type = self._detect_emergency_vehicle(frame, bbox)
                
                # Determine which direction this vehicle is in
                for direction in self.direction_counts:
                    if self._is_in_roi(centroid, frame.shape, direction):
                        self.direction_counts[direction] += 1
                        
                        # Draw bounding box with direction color
                        colors = {
                            'NORTH': (255, 0, 0),
                            'EAST': (0, 255, 0),
                            'SOUTH': (0, 0, 255),
                            'WEST': (255, 255, 0)
                        }
                        
                        # Use special color for emergency vehicles
                        # Only trigger emergency if cooldown has passed (prevent spam)
                        EMERGENCY_COOLDOWN_FRAMES = 300  # ~10 seconds at 30fps
                        if is_emergency and self.emergency_cooldown > EMERGENCY_COOLDOWN_FRAMES:
                            color = (0, 0, 255)  # Bright red for emergency
                            self.emergency_detected = True
                            self.emergency_direction = direction
                            self.emergency_cooldown = 0  # Reset cooldown
                            logger.warning(f"🚨 EMERGENCY VEHICLE ({emergency_type}) detected in {direction}!")
                        elif is_emergency:
                            # Emergency detected but in cooldown
                            color = (128, 0, 255)  # Purple = emergency but on cooldown
                            logger.debug(f"Emergency on cooldown: {self.emergency_cooldown}/{EMERGENCY_COOLDOWN_FRAMES}")
                        else:
                            color = colors[direction]
                        
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2 if not is_emergency else 4)
                        
                        # Draw ID and direction (with EMERGENCY label)
                        if is_emergency:
                            label = f"🚨 EMERGENCY {emergency_type.upper()}"
                            cv2.putText(annotated_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 3)
                        else:
                            label = f"ID:{obj_id} {direction}"
                            cv2.putText(annotated_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        # Draw centroid
                        cx, cy = map(int, centroid)
                        cv2.circle(annotated_frame, (cx, cy), 4, color, -1)
                        
                        break  # Vehicle counted in one direction only
            
            # Calculate FPS
            self.frame_count += 1
            current_time = time.time()
            elapsed = current_time - self.last_time
            
            if elapsed > 1.0:  # Update FPS every second
                self.fps = self.frame_count / elapsed
                self.frame_count = 0
                self.last_time = current_time
            
            # Draw statistics overlay
            total_vehicles = sum(self.direction_counts.values())
            stats_text = [
                f"FPS: {self.fps:.1f}",
                f"Total Vehicles: {total_vehicles}",
                f"N:{self.direction_counts['NORTH']} E:{self.direction_counts['EAST']}",
                f"S:{self.direction_counts['SOUTH']} W:{self.direction_counts['WEST']}"
            ]
            
            y_offset = 30
            for text in stats_text:
                cv2.putText(
                    annotated_frame,
                    text,
                    (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2
                )
                y_offset += 25
            
            return annotated_frame, self.direction_counts, tracked_objects
            
        except Exception as e:
            logger.error(f"Error in vehicle detection: {e}")
            return frame, self.direction_counts, {}
    
    # Legacy method for backward compatibility
    def detect_cars(self, frame):
        """
        Legacy method for backward compatibility
        Returns: (annotated_frame, total_car_count)
        """
        annotated_frame, direction_counts, _ = self.detect_vehicles(frame, draw_roi=True)
        total_count = sum(direction_counts.values())
        return annotated_frame, total_count
    
    def get_car_count(self):
        """Get total vehicle count across all directions"""
        with self.lock:
            return sum(self.direction_counts.values())
    
    def get_direction_counts(self):
        """Get vehicle counts per direction"""
        with self.lock:
            return self.direction_counts.copy()
    
    def get_fps(self):
        """Get current processing FPS"""
        return self.fps
    
    def is_emergency_detected(self):
        """Check if an emergency vehicle is currently detected"""
        return self.emergency_detected
    
    def get_emergency_info(self):
        """Get emergency vehicle detection info"""
        return {
            'detected': self.emergency_detected,
            'direction': self.emergency_direction,
            'cooldown_frames': self.emergency_cooldown
        }
    
    def configure_zones(self, zones_config):
        """
        Configure detection zones from settings
        
        Args:
            zones_config: Dict with zone configurations
                {
                    'NORTH': {'x1': 0.0, 'y1': 0.0, 'x2': 0.5, 'y2': 0.5, 'enabled': True},
                    ...
                }
        """
        for direction, config in zones_config.items():
            if direction in self.roi_zones and config.get('enabled', True):
                self.roi_zones[direction] = (
                    config.get('x1', 0),
                    config.get('y1', 0),
                    config.get('x2', 1),
                    config.get('y2', 1)
                )
                logger.info(f"Zone {direction} configured: {self.roi_zones[direction]}")
