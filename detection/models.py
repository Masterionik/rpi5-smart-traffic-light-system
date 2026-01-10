from django.db import models
from django.utils import timezone


class DetectionEvent(models.Model):
    """Stores each vehicle/pedestrian detection event"""
    EVENT_TYPES = [
        ('CAR', 'Car Detected'),
        ('PEDESTRIAN', 'Pedestrian Detected'),
        ('LED_CHANGE', 'LED State Changed'),
        ('SYSTEM', 'System Event'),
        ('EMERGENCY', 'Emergency Event'),
    ]
    
    DIRECTIONS = [
        ('NORTH', 'North'),
        ('EAST', 'East'),
        ('SOUTH', 'South'),
        ('WEST', 'West'),
    ]
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    direction = models.CharField(max_length=10, choices=DIRECTIONS, null=True, blank=True)
    message = models.TextField()
    vehicle_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_type', 'timestamp']),
        ]
    
    def __str__(self):
        return f"[{self.timestamp}] {self.event_type}: {self.message}"


class VehicleCount(models.Model):
    """Stores vehicle count snapshots for analytics"""
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    north_count = models.IntegerField(default=0)
    east_count = models.IntegerField(default=0)
    south_count = models.IntegerField(default=0)
    west_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"[{self.timestamp}] N:{self.north_count} E:{self.east_count} S:{self.south_count} W:{self.west_count}"


class TrafficLightState(models.Model):
    """Stores traffic light state changes"""
    LED_STATES = [
        ('RED', 'Red'),
        ('YELLOW', 'Yellow'),
        ('GREEN', 'Green'),
        ('RED_YELLOW', 'Red+Yellow'),
        ('OFF', 'Off'),
    ]
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    state = models.CharField(max_length=15, choices=LED_STATES)
    direction = models.CharField(max_length=10, null=True, blank=True)
    triggered_by = models.CharField(max_length=50, default='AUTO')  # AUTO, MANUAL, DETECTION, PEDESTRIAN
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"[{self.timestamp}] {self.state} - {self.triggered_by}"


class SystemStats(models.Model):
    """Daily system statistics"""
    date = models.DateField(unique=True, db_index=True)
    total_vehicles_detected = models.IntegerField(default=0)
    total_pedestrian_requests = models.IntegerField(default=0)
    total_light_cycles = models.IntegerField(default=0)
    total_emergency_stops = models.IntegerField(default=0)
    uptime_seconds = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"Stats for {self.date}: {self.total_vehicles_detected} vehicles"


class HourlyStats(models.Model):
    """Hourly traffic statistics for peak hour analysis"""
    date = models.DateField(db_index=True)
    hour = models.IntegerField(db_index=True)  # 0-23
    north_total = models.IntegerField(default=0)
    east_total = models.IntegerField(default=0)
    south_total = models.IntegerField(default=0)
    west_total = models.IntegerField(default=0)
    total_vehicles = models.IntegerField(default=0)
    avg_green_time = models.FloatField(default=0)
    
    class Meta:
        ordering = ['-date', '-hour']
        unique_together = ['date', 'hour']
    
    def __str__(self):
        return f"{self.date} {self.hour}:00 - {self.total_vehicles} vehicles"


class CameraSource(models.Model):
    """Multi-camera support - register different camera sources"""
    CAMERA_TYPES = [
        ('RPI', 'Raspberry Pi Camera'),
        ('USB', 'USB Camera'),
        ('IP', 'IP Camera'),
        ('DROIDCAM', 'DroidCam (Phone)'),
    ]
    
    name = models.CharField(max_length=100)
    camera_type = models.CharField(max_length=20, choices=CAMERA_TYPES)
    location = models.CharField(max_length=200, blank=True)  # e.g., "North entrance"
    url = models.CharField(max_length=500, blank=True)  # For IP cameras
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Direction mappings for this camera
    primary_direction = models.CharField(max_length=10, default='NORTH')
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.camera_type})"


class CameraVehicleCount(models.Model):
    """Vehicle counts per camera for multi-camera aggregation"""
    camera = models.ForeignKey(CameraSource, on_delete=models.CASCADE, related_name='counts')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    vehicle_count = models.IntegerField(default=0)
    direction = models.CharField(max_length=10, default='NORTH')
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"[{self.camera.name}] {self.timestamp}: {self.vehicle_count}"


class WeatherData(models.Model):
    """Weather data for traffic correlation"""
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    temperature = models.FloatField(null=True)  # Celsius
    humidity = models.FloatField(null=True)  # Percentage
    weather_condition = models.CharField(max_length=50, blank=True)  # e.g., "Clear", "Rain", "Snow"
    weather_description = models.CharField(max_length=200, blank=True)
    wind_speed = models.FloatField(null=True)  # m/s
    visibility = models.IntegerField(null=True)  # meters
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.timestamp}: {self.weather_condition} {self.temperature}°C"


class TrafficPrediction(models.Model):
    """Store traffic predictions for future reference"""
    created_at = models.DateTimeField(auto_now_add=True)
    prediction_for = models.DateTimeField(db_index=True)  # When this prediction is for
    predicted_north = models.IntegerField(default=0)
    predicted_east = models.IntegerField(default=0)
    predicted_south = models.IntegerField(default=0)
    predicted_west = models.IntegerField(default=0)
    predicted_total = models.IntegerField(default=0)
    confidence = models.FloatField(default=0)  # 0-1 confidence score
    model_version = models.CharField(max_length=50, default='v1')
    
    class Meta:
        ordering = ['-prediction_for']
    
    def __str__(self):
        return f"Prediction for {self.prediction_for}: {self.predicted_total} vehicles"


class SystemSettings(models.Model):
    """
    Persistent system settings stored in database
    Only one record should exist (singleton pattern)
    """
    # DroidCam settings
    droidcam_url = models.CharField(max_length=255, blank=True, default='')
    droidcam_enabled = models.BooleanField(default=False)
    droidcam_flip_horizontal = models.BooleanField(default=False)
    droidcam_flip_vertical = models.BooleanField(default=False)
    droidcam_rotation = models.IntegerField(default=0, choices=[
        (0, '0° (Normal)'),
        (90, '90° Clockwise'),
        (180, '180° Upside Down'),
        (270, '270° Counter-clockwise'),
    ])
    
    # RPi Camera settings
    rpi_camera_flip_horizontal = models.BooleanField(default=False)
    rpi_camera_flip_vertical = models.BooleanField(default=False)
    rpi_camera_rotation = models.IntegerField(default=180)  # Default upside down for typical mount
    
    # Pedestrian Phone Mode
    pedestrian_phone_mode_enabled = models.BooleanField(default=False)
    
    # Last updated
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"
    
    def __str__(self):
        return f"System Settings (updated: {self.updated_at})"
    
    @classmethod
    def get_settings(cls):
        """Get or create singleton settings instance"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def save(self, *args, **kwargs):
        """Ensure only one instance exists"""
        self.pk = 1
        super().save(*args, **kwargs)

