import cv2
import threading
import numpy as np
import json
from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import condition
from django.views.decorators.csrf import csrf_exempt
import logging
import platform
from detector.yolo_detector import YOLODetector
from detector.traffic_controller import TrafficController
from detector.pedestrian_detector import PedestrianGestureDetector
from hardware.led_strip import LEDStripController
from camera.droidcam import DroidCamHandler

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
        
        # Camera rotation (0, 90, 180, 270)
        self.rotation = 180  # Camera mounted upside down
        
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
            
            # Try multiple camera indices (0, 1, 2)
            camera_opened = False
            for cam_idx in [0, 1, 2]:
                logger.info(f"Trying camera index {cam_idx}")
                self.video = cv2.VideoCapture(cam_idx)
                
                if self.video.isOpened():
                    # Test if we can actually read a frame
                    ret, test_frame = self.video.read()
                    if ret and test_frame is not None:
                        logger.info(f"Camera {cam_idx} works - got test frame")
                        camera_opened = True
                        break
                    else:
                        logger.warning(f"Camera {cam_idx} opened but cannot read frames")
                        self.video.release()
                else:
                    logger.warning(f"Camera {cam_idx} failed to open")
            
            if not camera_opened:
                logger.error("Cannot open any camera with OpenCV (tried indices 0, 1, 2)")
                return False
            
            # Configure camera
            self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.video.set(cv2.CAP_PROP_FPS, 30)
            
            # Read initial frame to warm up camera
            ret, self.frame = self.video.read()
            if ret:
                logger.info(f"Initial frame: {self.frame.shape}")
            
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
                    
                    # Apply rotation if needed (180 degrees for upside-down mount)
                    if self.rotation == 180:
                        frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_180)
                    elif self.rotation == 90:
                        frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
                    elif self.rotation == 270:
                        frame_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    
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
        consecutive_failures = 0
        max_consecutive_failures = 30  # Allow 30 consecutive failures before giving up
        
        while self.is_running:
            ret, frame = self.video.read()
            
            if ret and frame is not None:
                # Apply rotation if needed (180 degrees for upside-down mount)
                if self.rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif self.rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif self.rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    
                with self.lock:
                    self.frame = frame
                consecutive_failures = 0  # Reset counter on success
            else:
                consecutive_failures += 1
                if consecutive_failures == 1:  # Log only first failure
                    logger.warning(f"Failed to read frame from camera")
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"Camera failed {max_consecutive_failures} times consecutively, stopping")
                    break
                    
                # Wait a bit before retrying
                import time
                time.sleep(0.1)
    
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

# Initialize traffic controller
if led_strip:
    traffic_controller = TrafficController(led_strip)
    traffic_controller.start()
    logger.info("Traffic controller started")
else:
    traffic_controller = None
    logger.warning("Traffic controller not initialized (LED strip unavailable)")

# Initialize DroidCam handler
droidcam = DroidCamHandler()
pedestrian_detector = PedestrianGestureDetector()


def gen_frames():
    """Generator function for streaming video frames with YOLO detection and traffic control"""
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
            # Use enhanced detection with ROI and tracking
            frame, direction_counts, tracked_objects = camera.detector.detect_vehicles(frame, draw_roi=True)
            
            # Update car count
            with camera.lock:
                camera.car_count = sum(direction_counts.values())
            
            # Update traffic controller with vehicle counts
            if traffic_controller:
                traffic_controller.update_vehicle_counts(direction_counts)
        else:
            # No detection, reset counts
            if traffic_controller:
                traffic_controller.update_vehicle_counts({d: 0 for d in TrafficController.DIRECTIONS})

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
    return render(request, 'camera/dashboard.html', {'page': 'dashboard'})


def analytics(request):
    """Display analytics and logs page"""
    return render(request, 'camera/analytics.html', {'page': 'analytics'})


def cameras(request):
    """Display camera feeds page"""
    return render(request, 'camera/cameras.html', {'page': 'cameras'})


def settings_page(request):
    """Display settings page"""
    return render(request, 'camera/settings.html', {'page': 'settings'})


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
def set_traffic_mode(request):
    """Set traffic control mode (AUTO/MANUAL)"""
    if not traffic_controller:
        return JsonResponse({'error': 'Traffic controller not available'}, status=503)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            mode = data.get('mode', 'AUTO').upper()
            
            if mode not in ['AUTO', 'MANUAL']:
                return JsonResponse({'error': 'Invalid mode'}, status=400)
            
            success = traffic_controller.set_mode(mode)
            return JsonResponse({
                'success': success,
                'mode': mode,
                'message': f'Mode set to {mode}'
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request required'}, status=400)


@csrf_exempt
def manual_control_light(request):
    """Manually control a traffic light (MANUAL mode only)"""
    if not traffic_controller:
        return JsonResponse({'error': 'Traffic controller not available'}, status=503)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            direction = data.get('direction')
            state = data.get('state', 'RED').upper()
            
            if not direction:
                return JsonResponse({'error': 'Direction required'}, status=400)
            
            success = traffic_controller.manual_set_direction(direction, state)
            
            if success:
                return JsonResponse({
                    'success': True,
                    'direction': direction,
                    'state': state
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Manual control requires MANUAL mode'
                }, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request required'}, status=400)


@csrf_exempt
def request_pedestrian_crossing(request):
    """Request pedestrian crossing"""
    if not traffic_controller:
        return JsonResponse({'error': 'Traffic controller not available'}, status=503)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            direction = data.get('direction', 'NORTH')
            
            success = traffic_controller.request_pedestrian_crossing(direction)
            
            return JsonResponse({
                'success': success,
                'direction': direction,
                'message': 'Request accepted' if success else 'Request in cooldown'
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request required'}, status=400)


def traffic_status(request):
    """Get complete traffic control system status"""
    if not traffic_controller:
        return JsonResponse({'error': 'Traffic controller not available'}, status=503)
    
    status = traffic_controller.get_status()
    
    # Add detector stats
    status['detector'] = {
        'enabled': camera.detector_enabled,
        'fps': camera.detector.get_fps(),
        'direction_counts': camera.detector.get_direction_counts()
    }
    
    return JsonResponse(status)


def event_log(request):
    """Get event log"""
    if not traffic_controller:
        return JsonResponse({'error': 'Traffic controller not available'}, status=503)
    
    limit = int(request.GET.get('limit', 50))
    events = traffic_controller.get_event_log(limit=limit)
    
    return JsonResponse({'events': events})


@csrf_exempt
def emergency_stop(request):
    """Emergency stop - set all lights to red"""
    if not traffic_controller:
        return JsonResponse({'error': 'Traffic controller not available'}, status=503)
    
    if request.method == 'POST':
        traffic_controller.emergency_stop()
        return JsonResponse({
            'success': True,
            'message': 'Emergency stop activated - all lights RED'
        })
    
    return JsonResponse({'error': 'POST request required'}, status=400)


@csrf_exempt
def test_led(request):
    """Test LED strip functionality"""
    if not led_strip:
        return JsonResponse({'error': 'LED strip not available'}, status=503)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            color = data.get('color', 'off').upper()
            brightness = data.get('brightness', None)
            
            # Set brightness if provided
            if brightness is not None:
                try:
                    led_strip.brightness = int(brightness) / 100.0
                except (ValueError, TypeError):
                    pass
            
            # Set the color/state
            valid_colors = ['RED', 'YELLOW', 'GREEN', 'ALL_ON', 'OFF']
            if color in valid_colors:
                led_strip.set_state(color)
                return JsonResponse({
                    'success': True,
                    'message': f'LED strip set to {color}',
                    'color': color,
                    'enabled': led_strip.enabled
                })
            else:
                return JsonResponse({
                    'error': f'Invalid color. Use: {valid_colors}'
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"LED test error: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    # GET request - return LED status
    return JsonResponse({
        'enabled': led_strip.enabled,
        'current_state': led_strip._current_state if hasattr(led_strip, '_current_state') else 'UNKNOWN',
        'num_pixels': led_strip.num_pixels,
        'brightness': int(led_strip.brightness * 100)
    })


@csrf_exempt
def start_droidcam(request):
    """Start DroidCam connection"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            url = data.get('url', 'http://192.168.1.100:4747/mjpegfeed')
            
            droidcam.droidcam_url = url
            success = droidcam.start()
            
            if success:
                # Load pedestrian detector model (shared with main YOLO)
                pedestrian_detector.load_model()
                
                return JsonResponse({
                    'success': True,
                    'message': 'DroidCam connected',
                    'url': url
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': droidcam.error_msg
                }, status=503)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request required'}, status=400)


def droidcam_feed(request):
    """Stream DroidCam video feed with pedestrian gesture detection"""
    def gen_droidcam_frames():
        while droidcam.is_running:
            frame = droidcam.get_frame()
            
            if frame is None:
                continue
            
            # Apply pedestrian gesture detection
            if pedestrian_detector.is_loaded:
                gesture_detected, confidence, annotated_frame, direction = pedestrian_detector.detect_gesture(
                    frame, draw_overlay=True
                )
                
                if gesture_detected and direction and traffic_controller:
                    # Send crossing request
                    traffic_controller.request_pedestrian_crossing(direction)
                    logger.info(f"Pedestrian gesture detected - requesting crossing for {direction}")
                
                frame = annotated_frame
            
            # Encode frame
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' +
                       frame_bytes + b'\r\n')
    
    return StreamingHttpResponse(
        gen_droidcam_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def droidcam_status(request):
    """Get DroidCam status"""
    status = {
        'connected': droidcam.is_connected,
        'running': droidcam.is_running,
        'url': droidcam.droidcam_url,
        'error': droidcam.error_msg,
        'pedestrian_detector': pedestrian_detector.get_status()
    }
    
    return JsonResponse(status)


@csrf_exempt
def shutdown_camera(request):
    """Shutdown camera gracefully"""
    global camera
    camera.release()
    
    if traffic_controller:
        traffic_controller.stop()
    
    if led_strip:
        led_strip.off()
    
    if droidcam.is_running:
        droidcam.stop()
    
    return JsonResponse({'status': 'System shutdown complete'})


