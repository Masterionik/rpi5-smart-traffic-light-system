#!/usr/bin/env python3
"""
Setup script to configure libcamera access in virtual environment
Run this after creating the venv on Raspberry Pi
"""
import sys
import os
import site

def setup_libcamera_path():
    """Add system libcamera to venv path"""
    
    # Get site-packages directory
    site_packages = site.getsitepackages()[0] if hasattr(site, 'getsitepackages') else site.USER_SITE
    
    pth_file = os.path.join(site_packages, 'system-packages.pth')
    system_dist_packages = '/usr/lib/python3/dist-packages'
    
    # Check if libcamera exists in system packages
    libcamera_path = os.path.join(system_dist_packages, 'libcamera')
    
    if not os.path.exists(libcamera_path):
        print(f"ERROR: libcamera not found at {libcamera_path}")
        print("Please install: sudo apt-get install python3-libcamera")
        return False
    
    # Create .pth file
    try:
        with open(pth_file, 'w') as f:
            f.write('/usr/lib/python3/dist-packages\n')
        print(f"✓ Created {pth_file}")
    except Exception as e:
        print(f"ERROR: Could not write to {pth_file}: {e}")
        return False
    
    # Verify import works
    try:
        import libcamera
        print(f"✓ libcamera imported successfully from: {libcamera.__file__}")
        return True
    except ImportError as e:
        print(f"ERROR: Could not import libcamera: {e}")
        return False

if __name__ == '__main__':
    print("Setting up libcamera access...")
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")
    
    if setup_libcamera_path():
        print("\n✓ Setup completed successfully!")
        sys.exit(0)
    else:
        print("\n✗ Setup failed!")
        sys.exit(1)
