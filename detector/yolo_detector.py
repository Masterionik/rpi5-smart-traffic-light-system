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
    """
    
    # COCO dataset vehicle classes
    VEHICLE_CLASSES = {
        2: 'car',
        3: 'motorcycle', 
        5: 'bus',
        7: 'truck'
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
            
            # Count vehicles per direction and draw annotations
            for obj_id, (centroid, bbox) in tracked_objects.items():
                x1, y1, x2, y2 = bbox
                
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
                        color = colors[direction]
                        
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                        
                        # Draw ID and direction
                        label = f"ID:{obj_id} {direction}"
                        cv2.putText(
                            annotated_frame,
                            label,
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2
                        )
                        
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
