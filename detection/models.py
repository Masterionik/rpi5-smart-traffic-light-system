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

