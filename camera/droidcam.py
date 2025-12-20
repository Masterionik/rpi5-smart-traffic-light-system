import cv2
import threading
import logging
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

class DroidCamHandler:
    """
    Handles video stream from DroidCam (iPhone camera app)
    DroidCam provides HTTP MJPEG stream
    """
    def __init__(self, droidcam_url='http://192.168.1.100:4747/mjpegfeed'):
        """
        Initialize DroidCam handler
        droidcam_url: HTTP address of DroidCam stream (e.g., http://iphone-ip:4747/mjpegfeed)
        """
        self.droidcam_url = droidcam_url
        self.frame = None
        self.lock = threading.Lock()
        self.is_running = False
        self.thread = None
        self.is_connected = False
        self.error_msg = ""
        
    def start(self):
        """Start reading from DroidCam"""
        try:
            # Normalize URL - ensure it has proper format
            url = self.droidcam_url.strip()
            
            # Add protocol if missing
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'http://' + url
            
            # Add default endpoint if just IP:port
            if not url.endswith('/mjpegfeed') and not url.endswith('/stream') and not url.endswith('/video'):
                if url.rstrip('/').count('/') == 2:  # Only protocol and domain, no path
                    url = url.rstrip('/') + '/mjpegfeed'
            
            logger.info(f"Testing DroidCam connection at {url}")
            
            # Test connection with GET request (DroidCam might not like HEAD)
            try:
                response = requests.get(url, stream=True, timeout=5, verify=False)
                
                if response.status_code == 200:
                    logger.info(f"DroidCam HTTP 200 OK")
                elif response.status_code in [400, 401, 403]:
                    # DroidCam might return these but still work
                    logger.warning(f"DroidCam returned HTTP {response.status_code} - may still work")
                elif response.status_code == 404:
                    self.error_msg = f"DroidCam endpoint not found (404). Check endpoint URL."
                    logger.error(self.error_msg)
                    return False
                elif response.status_code >= 500:
                    self.error_msg = f"DroidCam server error (HTTP {response.status_code})"
                    logger.error(self.error_msg)
                    return False
                else:
                    self.error_msg = f"DroidCam returned status {response.status_code}"
                    logger.warning(self.error_msg)
                
                logger.info("DroidCam connection successful")
                self.droidcam_url = url  # Update with normalized URL
                self.is_connected = True
                self.is_running = True
                
                # Start reading frames in background thread
                self.thread = threading.Thread(target=self._read_frames)
                self.thread.daemon = True
                self.thread.start()
                
                return True
                
            except requests.exceptions.Timeout:
                self.error_msg = "DroidCam connection timeout - device may be offline or wrong IP"
                logger.error(self.error_msg)
                self.is_connected = False
                return False
            except requests.exceptions.ConnectionError as e:
                self.error_msg = f"Cannot connect to DroidCam - check IP address and port"
                logger.error(f"{self.error_msg}: {e}")
                self.is_connected = False
                return False
                
        except Exception as e:
            self.error_msg = f"DroidCam error: {str(e)}"
            logger.error(self.error_msg)
            self.is_connected = False
            return False
    
    def _read_frames(self):
        """Continuously read MJPEG frames from DroidCam"""
        frames_received = 0
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        
        while self.is_running and reconnect_attempts < max_reconnect_attempts:
            try:
                # Set headers to identify ourselves and handle different DroidCam versions
                headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36',
                    'Connection': 'keep-alive',
                    'Accept': 'multipart/x-mixed-replace'
                }
                
                response = requests.get(self.droidcam_url, stream=True, timeout=30, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"DroidCam stream error: HTTP {response.status_code}")
                    logger.error(f"Response headers: {response.headers}")
                    self.is_connected = False
                    reconnect_attempts += 1
                    if self.is_running:
                        logger.info(f"Attempting reconnect ({reconnect_attempts}/{max_reconnect_attempts})...")
                        threading.Event().wait(3)  # Wait 3 seconds before retry
                    continue
                
                # Reset reconnect counter on successful connection
                reconnect_attempts = 0
                frames_received = 0
                
                # Log successful connection
                logger.info(f"DroidCam stream started. Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                
                # Parse MJPEG stream
                bytes_data = b''
                consecutive_decode_errors = 0
                
                for chunk in response.iter_content(chunk_size=4096):
                    if not self.is_running:
                        break
                    
                    if chunk:
                        bytes_data += chunk
                        
                        # Find JPEG frame boundaries
                        a = bytes_data.find(b'\xff\xd8')  # JPEG start
                        b = bytes_data.find(b'\xff\xd9')  # JPEG end
                        
                        if a != -1 and b != -1:
                            jpg_data = bytes_data[a:b+2]
                            bytes_data = bytes_data[b+2:]
                            
                            # Decode JPEG
                            try:
                                import numpy as np
                                nparr = np.frombuffer(jpg_data, np.uint8)
                                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                
                                if frame is not None:
                                    with self.lock:
                                        self.frame = frame
                                    frames_received += 1
                                    consecutive_decode_errors = 0
                                    
                                    # Log first frame and occasional updates
                                    if frames_received == 1:
                                        logger.info(f"DroidCam first frame received. Size: {frame.shape}")
                                    elif frames_received % 100 == 0:
                                        logger.debug(f"DroidCam frames received: {frames_received}")
                                else:
                                    consecutive_decode_errors += 1
                                    logger.warning(f"Failed to decode JPEG frame (size: {len(jpg_data)} bytes)")
                                    
                                    # If too many decode errors, the encoder might be broken
                                    if consecutive_decode_errors > 10:
                                        logger.error("Too many decode errors - encoder likely broken on Android")
                                        break
                            except Exception as e:
                                consecutive_decode_errors += 1
                                logger.warning(f"Error decoding DroidCam frame: {e}")
                    
            except requests.exceptions.ConnectionError as e:
                logger.error(f"DroidCam connection lost: {e}")
                self.is_connected = False
                reconnect_attempts += 1
                if self.is_running and reconnect_attempts < max_reconnect_attempts:
                    logger.info(f"Attempting reconnect ({reconnect_attempts}/{max_reconnect_attempts})...")
                    threading.Event().wait(3)
                    
            except requests.exceptions.Timeout:
                logger.error("DroidCam stream timeout")
                self.is_connected = False
                reconnect_attempts += 1
                if self.is_running and reconnect_attempts < max_reconnect_attempts:
                    logger.info(f"Attempting reconnect ({reconnect_attempts}/{max_reconnect_attempts})...")
                    threading.Event().wait(3)
                    
            except Exception as e:
                logger.error(f"DroidCam stream error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.is_connected = False
                reconnect_attempts += 1
                if self.is_running and reconnect_attempts < max_reconnect_attempts:
                    logger.info(f"Attempting reconnect ({reconnect_attempts}/{max_reconnect_attempts})...")
                    threading.Event().wait(3)
        
        self.is_running = False
        self.is_connected = False
        logger.info(f"DroidCam stream ended. Total frames: {frames_received}, Reconnect attempts: {reconnect_attempts}")
    
    def get_frame(self):
        """Get current frame"""
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
        return None
    
    def stop(self):
        """Stop reading frames"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.is_connected = False
        logger.info("DroidCam stopped")
    
    def is_active(self):
        """Check if DroidCam is active and reading frames"""
        return self.is_running and self.is_connected
