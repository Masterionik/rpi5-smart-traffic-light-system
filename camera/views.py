import cv2
import threading
import numpy as np
from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import condition
from django.views.decorators.csrf import csrf_exempt
import logging
import platform
from detector.yolo_detector import YOLODetector
from hardware.led_strip import LEDStripController

logger = logging.getLogger(__name__)

class VideoCamera:
    """
    Handles video capture from Raspberry Pi Camera Module 3
    with YOLO car detection
    Optimized for low-resource Raspberry Pi 5 environment
    """
    def __init__(self):
        self.video = None
        self.frame = None
        self.lock = threading.Lock()
        self.is_running = False
        self.thread = None
        self.picamera2 = None
        self.is_rpi = platform.machine() in ('armv7l', 'armv6l', 'aarch64')
        
        # YOLO detector
        self.detector = YOLODetector(model_name='yolov8n.pt')  # nano model for RPi
        self.detector_enabled = False
        self.car_count = 0
        
    def init_camera(self):
        """Initialize camera with native picamera2 for Raspberry Pi or OpenCV fallback"""
        try:
            # Try picamera2 first (works on Raspberry Pi)
            try:
                import sys
                logger.info(f"Python path: {sys.executable}")
                logger.info(f"Python version: {sys.version}")
                
                from picamera2 import Picamera2
                logger.info("picamera2 import successful")
                
                self.picamera2 = Picamera2()
                logger.info("Picamera2 object created")
                
                # Configure camera for balanced quality/performance
                config = self.picamera2.create_preview_configuration(
                    main={"format": "RGB888", "size": (640, 480)}
                )
                logger.info("Camera config created")
                
                self.picamera2.configure(config)
                logger.info("Camera configured")
                
                self.picamera2.start()
                logger.info("Camera started")
                
                self.is_running = True
                self.thread = threading.Thread(target=self._read_frames_picamera2)
                self.thread.daemon = True
                self.thread.start()
                logger.info("Picamera2 initialized successfully")
                return True
                
            except ImportError as e:
                logger.warning(f"picamera2 ImportError: {e}, trying OpenCV")
                import traceback
                logger.warning(traceback.format_exc())
            except Exception as e:
                logger.warning(f"picamera2 initialization failed: {e}, trying OpenCV")
                import traceback
                logger.warning(traceback.format_exc())
            
            # Fallback to OpenCV
            logger.info("Attempting OpenCV fallback")
            self.video = cv2.VideoCapture(0)
            
            if not self.video.isOpened():
                logger.error("Cannot open camera with OpenCV")
                return False
            
            self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.video.set(cv2.CAP_PROP_FPS, 30)
            
            self.is_running = True
            self.thread = threading.Thread(target=self._read_frames)
            self.thread.daemon = True
            self.thread.start()
            
            logger.info("OpenCV camera initialized (fallback)")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing camera: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _read_frames_picamera2(self):
        """Continuously read frames from picamera2"""
        try:
            while self.is_running:
                try:
                    request = self.picamera2.capture_request()
                    
                    # Get RGB data from the main stream
                    frame = request.make_array("main")
                    
                    # Convert RGB to BGR for OpenCV compatibility
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                    request.release()
                    
                    with self.lock:
                        self.frame = frame_bgr
                        
                except Exception as e:
                    logger.warning(f"Error capturing frame from picamera2: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
                    
        except Exception as e:
            logger.error(f"Picamera2 thread error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            if self.picamera2:
                try:
                    self.picamera2.stop()
                except:
                    pass
    
    def _read_frames(self):
        """Continuously read frames in background thread"""
        while self.is_running:
            ret, frame = self.video.read()
            
            if ret:
                with self.lock:
                    self.frame = frame
            else:
                logger.warning("Failed to read frame from camera")
                break
    
    def get_frame(self):
        """Get the latest frame"""
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
        return None
    
    def release(self):
        """Release camera resources"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.video:
            self.video.release()
        if self.picamera2:
            try:
                self.picamera2.stop()
            except:
                pass
        logger.info("Camera released")


# Global camera instance
camera = VideoCamera()
try:
    led_strip = LEDStripController(num_pixels=8, brightness=64)
except Exception as exc:
    led_strip = None
    logger.warning(f"LED strip not initialized: {exc}")


def gen_frames():
    """Generator function for streaming video frames with optional YOLO detection"""
    global camera
    
    if not camera.is_running:
        if not camera.init_camera():
            logger.error("Failed to initialize camera for streaming")
            return
    
    # Load YOLO model on first request if enabled
    if camera.detector_enabled and not camera.detector.is_loaded:
        camera.detector.load_model()
    
    while True:
        frame = camera.get_frame()
        
        if frame is None:
            continue
        
        # Apply YOLO detection if enabled
        if camera.detector_enabled and camera.detector.is_loaded:
            frame, car_count = camera.detector.detect_cars(frame)
            with camera.lock:
                camera.car_count = car_count
            if led_strip:
                if car_count > 0:
                    led_strip.set_green()
                else:
                    led_strip.set_red()
        else:
            if led_strip:
                led_strip.set_red()

        # Stream at up to 1080p (keeps aspect ratio, max width 1920)
        stream_frame = frame
        if frame.shape[1] > 1920:
            new_w = 1920
            new_h = int(frame.shape[0] * (1920.0 / frame.shape[1]))
            stream_frame = cv2.resize(frame, (new_w, new_h))

        # Encode frame to JPEG with higher quality for 1080p
        ret, buffer = cv2.imencode('.jpg', stream_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        
        if ret:
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' +
                   frame_bytes + b'\r\n')


def video_feed(request):
    """Stream video feed as MJPEG"""
    return StreamingHttpResponse(
        gen_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def dashboard(request):
    """Display web dashboard with video feed"""
    return render(request, 'camera/dashboard.html')


def camera_status(request):
    """API endpoint to check camera status"""
    global camera
    
    # Check if using picamera2 or OpenCV
    using_picamera2 = camera.picamera2 is not None
    using_opencv = camera.video is not None
    
    status = {
        'connected': camera.is_running,
        'camera_initialized': using_picamera2 or using_opencv,
        'backend': 'picamera2' if using_picamera2 else 'opencv' if using_opencv else 'none',
        'detection_enabled': camera.detector_enabled,
        'car_count': camera.car_count,
    }
    return JsonResponse(status)


@csrf_exempt
def toggle_detection(request):
    """Toggle YOLO car detection on/off"""
    global camera
    
    if request.method == 'POST':
        camera.detector_enabled = not camera.detector_enabled
        
        # Load model if enabling for first time
        if camera.detector_enabled and not camera.detector.is_loaded:
            success = camera.detector.load_model()
            return JsonResponse({
                'detection_enabled': camera.detector_enabled,
                'model_loaded': success,
                'message': 'Car detection enabled' if success else 'Failed to load model'
            })
        
        return JsonResponse({
            'detection_enabled': camera.detector_enabled,
            'message': 'Car detection enabled' if camera.detector_enabled else 'Car detection disabled'
        })
    
    return JsonResponse({'error': 'POST request required'}, status=400)


def detection_stats(request):
    """Get current detection statistics"""
    global camera
    
    stats = {
        'detection_enabled': camera.detector_enabled,
        'cars_detected': camera.car_count,
        'model_loaded': camera.detector.is_loaded,
    }
    return JsonResponse(stats)


@csrf_exempt
def shutdown_camera(request):
    """Shutdown camera gracefully"""
    global camera
    camera.release()
    if led_strip:
        led_strip.off()
    return JsonResponse({'status': 'Camera shutdown'})


