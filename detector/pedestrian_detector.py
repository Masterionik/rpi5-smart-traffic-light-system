"""
Pedestrian Gesture Detection System
Detects pedestrian intent to cross using smartphone camera gesture recognition
"""

import cv2
import numpy as np
import logging
import time
from collections import deque
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class PedestrianGestureDetector:
    """
    Detects pedestrian crossing intent using smartphone camera
    
    Multi-layer detection:
    1. Traffic light detection in frame
    2. Camera orientation analysis
    3. Gesture persistence (>2 seconds)
    4. Proximity estimation
    """
    
    def __init__(self, yolo_model=None):
        """
        Initialize pedestrian gesture detector
        
        Args:
            yolo_model: Shared YOLO model instance (optional)
        """
        self.model = yolo_model
        self.is_loaded = False
        
        # Detection state
        self.gesture_start_time = None
        self.gesture_active = False
        self.last_detection_time = 0
        
        # History for persistence checking
        self.detection_history = deque(maxlen=60)  # 2 seconds at 30fps
        
        # Thresholds
        self.PERSISTENCE_THRESHOLD = 2.0  # seconds
        self.COOLDOWN_PERIOD = 5.0  # seconds between detections
        self.PROXIMITY_THRESHOLD = 0.15  # Normalized frame area
        
    def load_model(self, model_path='yolov8n.pt'):
        """Load YOLO model for traffic light detection"""
        try:
            if self.model is None:
                logger.info(f"Loading YOLO model for gesture detection: {model_path}")
                self.model = YOLO(model_path)
            
            self.is_loaded = True
            logger.info("Gesture detection model loaded")
            return True
        except Exception as e:
            logger.error(f"Failed to load gesture detection model: {e}")
            return False
    
    def _detect_traffic_light(self, frame):
        """
        Detect traffic light in frame
        
        Args:
            frame: Input frame (BGR)
            
        Returns:
            Tuple of (detected, bbox, confidence) or (False, None, 0)
        """
        if not self.is_loaded or self.model is None:
            return False, None, 0
        
        try:
            results = self.model(frame, verbose=False, conf=0.4)
            
            if results and len(results) > 0:
                result = results[0]
                
                # Class 9 is 'traffic light' in COCO dataset
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    if class_id == 9:  # Traffic light
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        bbox = (x1, y1, x2, y2)
                        return True, bbox, confidence
            
            return False, None, 0
            
        except Exception as e:
            logger.error(f"Error detecting traffic light: {e}")
            return False, None, 0
    
    def _estimate_proximity(self, bbox, frame_shape):
        """
        Estimate proximity based on traffic light size in frame
        
        Args:
            bbox: Bounding box (x1, y1, x2, y2)
            frame_shape: Frame shape (h, w, c)
            
        Returns:
            float: Normalized area (0-1)
        """
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = bbox
        
        bbox_width = x2 - x1
        bbox_height = y2 - y1
        bbox_area = bbox_width * bbox_height
        
        frame_area = h * w
        normalized_area = bbox_area / frame_area
        
        return normalized_area
    
    def _check_center_alignment(self, bbox, frame_shape):
        """
        Check if traffic light is reasonably centered in frame
        
        Args:
            bbox: Bounding box (x1, y1, x2, y2)
            frame_shape: Frame shape (h, w, c)
            
        Returns:
            bool: True if centered
        """
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = bbox
        
        # Calculate center
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        
        # Frame center
        frame_center_x = w / 2
        frame_center_y = h / 2
        
        # Check if within center region (40% of frame)
        x_deviation = abs(center_x - frame_center_x) / w
        y_deviation = abs(center_y - frame_center_y) / h
        
        return x_deviation < 0.3 and y_deviation < 0.3
    
    def detect_gesture(self, frame, draw_overlay=True):
        """
        Detect pedestrian crossing gesture
        
        Args:
            frame: Input frame from smartphone camera (BGR)
            draw_overlay: Whether to draw detection overlay
            
        Returns:
            Tuple of (gesture_detected, confidence, annotated_frame, direction)
        """
        current_time = time.time()
        annotated_frame = frame.copy() if draw_overlay else frame
        
        # Check cooldown
        if current_time - self.last_detection_time < self.COOLDOWN_PERIOD:
            remaining = int(self.COOLDOWN_PERIOD - (current_time - self.last_detection_time))
            if draw_overlay:
                cv2.putText(
                    annotated_frame,
                    f"Cooldown: {remaining}s",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )
            return False, 0.0, annotated_frame, None
        
        # Layer 1: Detect traffic light
        detected, bbox, confidence = self._detect_traffic_light(frame)
        
        if not detected:
            # Reset gesture if no detection
            self.gesture_start_time = None
            self.gesture_active = False
            self.detection_history.append(0)
            
            if draw_overlay:
                cv2.putText(
                    annotated_frame,
                    "Point camera at traffic light",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 165, 255),
                    2
                )
            
            return False, 0.0, annotated_frame, None
        
        # Layer 2: Check proximity (distance estimation)
        proximity = self._estimate_proximity(bbox, frame.shape)
        
        if proximity < self.PROXIMITY_THRESHOLD:
            if draw_overlay:
                cv2.putText(
                    annotated_frame,
                    "Move closer to traffic light",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 165, 255),
                    2
                )
            
            self.gesture_start_time = None
            self.detection_history.append(0)
            return False, 0.0, annotated_frame, None
        
        # Layer 3: Check center alignment (orientation)
        is_centered = self._check_center_alignment(bbox, frame.shape)
        
        if not is_centered:
            if draw_overlay:
                cv2.putText(
                    annotated_frame,
                    "Center traffic light in frame",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 165, 255),
                    2
                )
            
            self.gesture_start_time = None
            self.detection_history.append(0)
            return False, 0.0, annotated_frame, None
        
        # All conditions met - start/continue gesture tracking
        if self.gesture_start_time is None:
            self.gesture_start_time = current_time
            self.gesture_active = True
        
        self.detection_history.append(1)
        
        # Layer 4: Check persistence
        gesture_duration = current_time - self.gesture_start_time
        
        if draw_overlay:
            # Draw traffic light bbox
            x1, y1, x2, y2 = bbox
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
            
            # Draw progress bar
            progress = min(gesture_duration / self.PERSISTENCE_THRESHOLD, 1.0)
            bar_width = 400
            bar_height = 30
            bar_x = 10
            bar_y = 60
            
            # Background
            cv2.rectangle(
                annotated_frame,
                (bar_x, bar_y),
                (bar_x + bar_width, bar_y + bar_height),
                (50, 50, 50),
                -1
            )
            
            # Progress
            fill_width = int(bar_width * progress)
            color = (0, 255, 0) if progress >= 1.0 else (0, 165, 255)
            cv2.rectangle(
                annotated_frame,
                (bar_x, bar_y),
                (bar_x + fill_width, bar_y + bar_height),
                color,
                -1
            )
            
            # Text
            status_text = "CROSSING REQUEST SENT!" if progress >= 1.0 else "Hold steady..."
            cv2.putText(
                annotated_frame,
                status_text,
                (bar_x, bar_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2
            )
            
            # Timer
            cv2.putText(
                annotated_frame,
                f"{gesture_duration:.1f}s / {self.PERSISTENCE_THRESHOLD}s",
                (bar_x + bar_width + 10, bar_y + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )
            
            # Confidence and proximity info
            info_y = bar_y + bar_height + 30
            cv2.putText(
                annotated_frame,
                f"Detection confidence: {confidence:.2f}",
                (10, info_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1
            )
            cv2.putText(
                annotated_frame,
                f"Proximity: {proximity:.3f}",
                (10, info_y + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1
            )
        
        # Check if gesture is complete
        if gesture_duration >= self.PERSISTENCE_THRESHOLD:
            logger.info(f"Pedestrian gesture detected! Duration: {gesture_duration:.1f}s")
            
            # Reset state
            self.gesture_start_time = None
            self.gesture_active = False
            self.last_detection_time = current_time
            
            # Determine direction based on frame position (simple heuristic)
            # In real implementation, this could use GPS or other location data
            direction = self._estimate_direction(bbox, frame.shape)
            
            return True, confidence, annotated_frame, direction
        
        return False, confidence, annotated_frame, None
    
    def _estimate_direction(self, bbox, frame_shape):
        """
        Estimate which direction the pedestrian wants to cross
        
        This is a simplified heuristic. In production, would use:
        - GPS location
        - Compass orientation
        - Map matching
        
        Args:
            bbox: Traffic light bounding box
            frame_shape: Frame shape
            
        Returns:
            str: Direction ('NORTH', 'EAST', 'SOUTH', 'WEST')
        """
        # Simple heuristic: based on where traffic light appears in frame
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = bbox
        
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        
        # Divide frame into quadrants
        if center_x < w / 2 and center_y < h / 2:
            return 'NORTH'
        elif center_x >= w / 2 and center_y < h / 2:
            return 'EAST'
        elif center_x >= w / 2 and center_y >= h / 2:
            return 'SOUTH'
        else:
            return 'WEST'
    
    def reset(self):
        """Reset gesture detection state"""
        self.gesture_start_time = None
        self.gesture_active = False
        self.detection_history.clear()
    
    def get_status(self):
        """Get current gesture detection status"""
        current_time = time.time()
        
        status = {
            'gesture_active': self.gesture_active,
            'gesture_duration': current_time - self.gesture_start_time if self.gesture_start_time else 0,
            'cooldown_remaining': max(0, self.COOLDOWN_PERIOD - (current_time - self.last_detection_time)),
            'detection_rate': sum(self.detection_history) / len(self.detection_history) if self.detection_history else 0
        }
        
        return status
