from django.contrib import admin
from .models import DetectionEvent, VehicleCount, TrafficLightState, SystemStats


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
