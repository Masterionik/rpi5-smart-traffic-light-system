from django.urls import path
from . import views

app_name = 'camera'

urlpatterns = [
    # Main pages
    path('', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics, name='analytics'),
    path('cameras/', views.cameras, name='cameras'),
    path('settings/', views.settings_page, name='settings_page'),
    
    # Primary camera (Raspberry Pi Camera Module 3)
    path('feed/', views.video_feed, name='video_feed'),
    path('status/', views.camera_status, name='camera_status'),
    path('shutdown/', views.shutdown_camera, name='shutdown_camera'),
    
    # Vehicle detection
    path('detection/toggle/', views.toggle_detection, name='toggle_detection'),
    path('detection/stats/', views.detection_stats, name='detection_stats'),
    
    # Traffic control
    path('traffic/status/', views.traffic_status, name='traffic_status'),
    path('traffic/mode/', views.set_traffic_mode, name='set_traffic_mode'),
    path('traffic/manual/', views.manual_control_light, name='manual_control_light'),
    path('traffic/emergency/', views.emergency_stop, name='emergency_stop'),
    path('traffic/events/', views.event_log, name='event_log'),
    
    # LED strip control
    path('led/test/', views.test_led, name='test_led'),
    
    # Pedestrian crossing
    path('pedestrian/request/', views.request_pedestrian_crossing, name='request_pedestrian_crossing'),
    
    # Settings backup/restore
    path('settings/backup/', views.backup_settings, name='backup_settings'),
    path('settings/restore/', views.restore_settings, name='restore_settings'),
    
    # Zone configuration
    path('zones/configure/', views.configure_zones, name='configure_zones'),
    
    # DroidCam (smartphone camera)
    path('droidcam/start/', views.start_droidcam, name='start_droidcam'),
    path('droidcam/feed/', views.droidcam_feed, name='droidcam_feed'),
    path('droidcam/status/', views.droidcam_status, name='droidcam_status'),
]
