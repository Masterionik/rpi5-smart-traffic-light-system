from django.urls import path
from . import views

app_name = 'camera'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    # Primary camera (Raspberry Pi)
    path('feed/', views.video_feed, name='video_feed'),
    path('status/', views.camera_status, name='camera_status'),
    path('shutdown/', views.shutdown_camera, name='shutdown_camera'),
    path('detection/toggle/', views.toggle_detection, name='toggle_detection'),
    path('detection/stats/', views.detection_stats, name='detection_stats'),
    
]
