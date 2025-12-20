import threading
import logging
from ultralytics import YOLO
import cv2
import numpy as np

logger = logging.getLogger(__name__)

class YOLODetector:
    """
    YOLO car detection for video frames
    Optimized for Raspberry Pi 5
    """
    def __init__(self, model_name='yolov8n.pt'):
        """
        Initialize YOLO detector
        model_name: 'yolov8n.pt' (nano - fastest), 'yolov8s.pt' (small), 'yolov8m.pt' (medium)
        For RPi5, use nano for best performance
        """
        self.model = None
        self.model_name = model_name
        self.lock = threading.Lock()
        self.detections = []
        self.is_loaded = False
        self.car_count = 0
        
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
    
    def detect_cars(self, frame):
        """
        Detect cars in frame and return annotated frame
        """
        if not self.is_loaded or self.model is None:
            return frame, 0
        
        try:
            # Run inference
            results = self.model(frame, verbose=False, conf=0.5)
            
            car_count = 0
            annotated_frame = frame.copy()
            
            # Process detections
            if results and len(results) > 0:
                result = results[0]
                
                # Filter for cars (class 2 in COCO dataset)
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    
                    # Class 2 is 'car' in COCO dataset
                    if class_id == 2:
                        car_count += 1
                        
                        # Get box coordinates
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        # Draw bounding box
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # Draw label with confidence
                        label = f"Car: {confidence:.2f}"
                        cv2.putText(
                            annotated_frame,
                            label,
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            2
                        )
                
                # Store detection count
                with self.lock:
                    self.car_count = car_count
            
            return annotated_frame, car_count
            
        except Exception as e:
            logger.error(f"Error in car detection: {e}")
            return frame, 0
    
    def get_car_count(self):
        """Get last detected car count"""
        with self.lock:
            return self.car_count
