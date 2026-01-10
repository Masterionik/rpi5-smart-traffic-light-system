from django.contrib import admin
from .models import (
    DetectionEvent, VehicleCount, TrafficLightState, SystemStats,
    HourlyStats, CameraSource, CameraVehicleCount, WeatherData, TrafficPrediction,
    SystemSettings
)


@admin.register(DetectionEvent)
class DetectionEventAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'event_type', 'direction', 'vehicle_count', 'message']
    list_filter = ['event_type', 'direction', 'timestamp']
    search_fields = ['message']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'


@admin.register(VehicleCount)
class VehicleCountAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'north_count', 'east_count', 'south_count', 'west_count', 'total_count']
    list_filter = ['timestamp']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'


@admin.register(TrafficLightState)
class TrafficLightStateAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'state', 'direction', 'triggered_by']
    list_filter = ['state', 'triggered_by', 'timestamp']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'


@admin.register(SystemStats)
class SystemStatsAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_vehicles_detected', 'total_pedestrian_requests', 'total_light_cycles']
    list_filter = ['date']
    ordering = ['-date']


@admin.register(HourlyStats)
class HourlyStatsAdmin(admin.ModelAdmin):
    list_display = ['date', 'hour', 'total_vehicles', 'north_total', 'east_total', 'south_total', 'west_total']
    list_filter = ['date', 'hour']
    ordering = ['-date', '-hour']


@admin.register(CameraSource)
class CameraSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'camera_type', 'location', 'is_active', 'primary_direction']
    list_filter = ['camera_type', 'is_active']
    search_fields = ['name', 'location']


@admin.register(CameraVehicleCount)
class CameraVehicleCountAdmin(admin.ModelAdmin):
    list_display = ['camera', 'timestamp', 'vehicle_count', 'direction']
    list_filter = ['camera', 'direction', 'timestamp']
    ordering = ['-timestamp']


@admin.register(WeatherData)
class WeatherDataAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'weather_condition', 'temperature', 'humidity', 'wind_speed']
    list_filter = ['weather_condition', 'timestamp']
    ordering = ['-timestamp']


@admin.register(TrafficPrediction)
class TrafficPredictionAdmin(admin.ModelAdmin):
    list_display = ['prediction_for', 'predicted_total', 'confidence', 'model_version', 'created_at']
    list_filter = ['model_version', 'prediction_for']
    ordering = ['-prediction_for']


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'droidcam_enabled', 'droidcam_url', 'pedestrian_phone_mode_enabled', 'updated_at']
    readonly_fields = ['updated_at']
    
    def has_add_permission(self, request):
        # Only allow one SystemSettings instance (singleton)
        if SystemSettings.objects.exists():
            return False
        return super().has_add_permission(request)
    
    def has_delete_permission(self, request, obj=None):
        return False
