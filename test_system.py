#!/usr/bin/env python3
"""
Test Script for Smart Traffic Light System
Run this to verify all components are working correctly
"""

import sys
import time

def print_test(test_name, status="RUNNING"):
    """Print test status"""
    colors = {
        "RUNNING": "\033[93m",  # Yellow
        "PASS": "\033[92m",      # Green
        "FAIL": "\033[91m",      # Red
        "SKIP": "\033[94m"       # Blue
    }
    reset = "\033[0m"
    
    symbols = {
        "RUNNING": "⏳",
        "PASS": "✅",
        "FAIL": "❌",
        "SKIP": "⏭️"
    }
    
    print(f"{colors[status]}{symbols[status]} {test_name}{reset}")


def test_imports():
    """Test all required imports"""
    print_test("Testing Python imports")
    
    try:
        import cv2
        print(f"  ✓ OpenCV version: {cv2.__version__}")
    except ImportError as e:
        print(f"  ✗ OpenCV import failed: {e}")
        return False
    
    try:
        from ultralytics import YOLO
        print(f"  ✓ YOLOv8 available")
    except ImportError as e:
        print(f"  ✗ YOLOv8 import failed: {e}")
        return False
    
    try:
        import django
        print(f"  ✓ Django version: {django.get_version()}")
    except ImportError as e:
        print(f"  ✗ Django import failed: {e}")
        return False
    
    try:
        import numpy
        print(f"  ✓ NumPy version: {numpy.__version__}")
    except ImportError as e:
        print(f"  ✗ NumPy import failed: {e}")
        return False
    
    print_test("Python imports", "PASS")
    return True


def test_hardware_imports():
    """Test hardware-specific imports"""
    print_test("Testing hardware imports")
    
    # Test LED strip
    try:
        from rpi_ws281x import PixelStrip, Color
        print(f"  ✓ rpi_ws281x available (LED control)")
    except ImportError:
        print(f"  ⚠ rpi_ws281x not available (OK if not on Raspberry Pi)")
    
    # Test picamera2
    try:
        from picamera2 import Picamera2
        print(f"  ✓ picamera2 available")
    except ImportError:
        print(f"  ⚠ picamera2 not available (OK if not on Raspberry Pi)")
    
    print_test("Hardware imports", "PASS")
    return True


def test_project_structure():
    """Test project file structure"""
    print_test("Testing project structure")
    
    import os
    
    required_files = [
        'manage.py',
        'requirements.txt',
        'myproject/settings.py',
        'camera/views.py',
        'camera/urls.py',
        'detector/yolo_detector.py',
        'detector/traffic_controller.py',
        'detector/pedestrian_detector.py',
        'hardware/led_strip.py',
        'camera/templates/camera/dashboard.html'
    ]
    
    all_found = True
    for file in required_files:
        if os.path.exists(file):
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} - NOT FOUND")
            all_found = False
    
    if all_found:
        print_test("Project structure", "PASS")
    else:
        print_test("Project structure", "FAIL")
    
    return all_found


def test_led_controller():
    """Test LED controller initialization"""
    print_test("Testing LED controller")
    
    try:
        from hardware.led_strip import LEDStripController
        
        # Initialize (may fail if not on Pi with LEDs)
        led = LEDStripController(num_pixels=8, brightness=64)
        
        if led.enabled:
            print(f"  ✓ LED controller initialized")
            print(f"  ✓ 8 LEDs configured")
            print(f"  ✓ 4 directions (2 LEDs each)")
            
            # Test methods exist
            assert hasattr(led, 'set_direction_state')
            assert hasattr(led, 'get_all_states')
            assert hasattr(led, 'transition_sequence')
            print(f"  ✓ All methods present")
            
            print_test("LED controller", "PASS")
            return True
        else:
            print(f"  ⚠ LED controller disabled (hardware not available)")
            print_test("LED controller", "SKIP")
            return True
            
    except Exception as e:
        print(f"  ✗ LED controller error: {e}")
        print_test("LED controller", "FAIL")
        return False


def test_yolo_detector():
    """Test YOLO detector"""
    print_test("Testing YOLO detector")
    
    try:
        from detector.yolo_detector import YOLODetector
        
        detector = YOLODetector(model_name='yolov8n.pt')
        
        # Check attributes
        assert hasattr(detector, 'load_model')
        assert hasattr(detector, 'detect_vehicles')
        assert hasattr(detector, 'get_direction_counts')
        print(f"  ✓ YOLODetector class OK")
        
        # Check tracker
        assert hasattr(detector, 'tracker')
        print(f"  ✓ Vehicle tracker initialized")
        
        # Check ROI zones
        assert len(detector.roi_zones) == 4
        print(f"  ✓ 4 ROI zones configured")
        
        print_test("YOLO detector", "PASS")
        return True
        
    except Exception as e:
        print(f"  ✗ YOLO detector error: {e}")
        print_test("YOLO detector", "FAIL")
        return False


def test_traffic_controller():
    """Test traffic controller"""
    print_test("Testing traffic controller")
    
    try:
        from detector.traffic_controller import TrafficController
        from hardware.led_strip import LEDStripController
        
        # Initialize with mock LED controller
        led = LEDStripController(num_pixels=8)
        controller = TrafficController(led)
        
        # Check attributes
        assert hasattr(controller, 'start')
        assert hasattr(controller, 'stop')
        assert hasattr(controller, 'update_vehicle_counts')
        assert hasattr(controller, 'request_pedestrian_crossing')
        print(f"  ✓ TrafficController class OK")
        
        # Check constants
        assert controller.T_MIN == 10
        assert controller.T_MAX == 60
        print(f"  ✓ Timing constants OK")
        
        # Check directions
        assert len(controller.DIRECTIONS) == 4
        print(f"  ✓ 4 directions configured")
        
        print_test("Traffic controller", "PASS")
        return True
        
    except Exception as e:
        print(f"  ✗ Traffic controller error: {e}")
        print_test("Traffic controller", "FAIL")
        return False


def test_pedestrian_detector():
    """Test pedestrian detector"""
    print_test("Testing pedestrian detector")
    
    try:
        from detector.pedestrian_detector import PedestrianGestureDetector
        
        detector = PedestrianGestureDetector()
        
        # Check attributes
        assert hasattr(detector, 'detect_gesture')
        assert hasattr(detector, 'load_model')
        assert hasattr(detector, 'get_status')
        print(f"  ✓ PedestrianGestureDetector class OK")
        
        # Check thresholds
        assert detector.PERSISTENCE_THRESHOLD == 2.0
        assert detector.COOLDOWN_PERIOD == 5.0
        print(f"  ✓ Detection thresholds OK")
        
        print_test("Pedestrian detector", "PASS")
        return True
        
    except Exception as e:
        print(f"  ✗ Pedestrian detector error: {e}")
        print_test("Pedestrian detector", "FAIL")
        return False


def test_django_settings():
    """Test Django configuration"""
    print_test("Testing Django settings")
    
    try:
        import os
        import sys
        
        # Add project to path
        sys.path.insert(0, os.getcwd())
        
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
        django.setup()
        
        from django.conf import settings
        
        # Check installed apps
        assert 'camera' in settings.INSTALLED_APPS
        assert 'detector' in settings.INSTALLED_APPS
        print(f"  ✓ Apps configured")
        
        # Check allowed hosts
        print(f"  ✓ ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
        
        print_test("Django settings", "PASS")
        return True
        
    except Exception as e:
        print(f"  ✗ Django settings error: {e}")
        print_test("Django settings", "FAIL")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("🔍 Smart Traffic Light System - Component Tests")
    print("="*60 + "\n")
    
    tests = [
        ("Imports", test_imports),
        ("Hardware Imports", test_hardware_imports),
        ("Project Structure", test_project_structure),
        ("LED Controller", test_led_controller),
        ("YOLO Detector", test_yolo_detector),
        ("Traffic Controller", test_traffic_controller),
        ("Pedestrian Detector", test_pedestrian_detector),
        ("Django Settings", test_django_settings)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print()
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            print_test(test_name, "FAIL")
            results.append((test_name, False))
        
        time.sleep(0.5)
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✅" if result else "❌"
        print(f"{symbol} {test_name}: {status}")
    
    print("\n" + "="*60)
    percentage = (passed / total) * 100
    print(f"Results: {passed}/{total} tests passed ({percentage:.1f}%)")
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to run.")
        print("\nNext steps:")
        print("  1. python manage.py runserver 0.0.0.0:8000")
        print("  2. Open http://<pi-ip>:8000/camera/")
        print("  3. Click 'Enable Detection' button")
        print("  4. Enjoy your smart traffic system! 🚦")
    elif percentage >= 75:
        print("\n⚠️  Most tests passed, but some issues detected.")
        print("   System may work with limited functionality.")
    else:
        print("\n❌ Multiple tests failed. Please fix issues before running.")
    
    print("="*60 + "\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
