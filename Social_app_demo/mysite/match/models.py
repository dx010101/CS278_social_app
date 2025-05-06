from django.db import models
import math
from django.db.models import F, Func, ExpressionWrapper, FloatField

# Create your models here.
class User(models.Model):
    user_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    interests = models.JSONField(default=list)
    hometown = models.CharField(max_length=255, blank=True, null=True)
    major = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.user_id})"
    
    @staticmethod
    def nearby_users(lat, lon, max_distance_km, exclude_user_id=None):
        """
        Find users within a specified distance using a bounding box first 
        (which is more efficient), then applying haversine calculation.
        
        Args:
            lat: Latitude of the center point
            lon: Longitude of the center point
            max_distance_km: Maximum distance in kilometers
            exclude_user_id: Optional user_id to exclude from results
        
        Returns:
            QuerySet of nearby users with distance field
        """
        # Earth's radius in kilometers
        R = 6371
        
        # Calculate bounding box (approximation)
        # This is more efficient than calculating haversine for all users
        lat_delta = math.degrees(max_distance_km / R)
        lon_delta = math.degrees(max_distance_km / (R * math.cos(math.radians(lat))))
        
        lat_min = lat - lat_delta
        lat_max = lat + lat_delta
        lon_min = lon - lon_delta
        lon_max = lon + lon_delta
        
        # Query users within bounding box
        queryset = User.objects.filter(
            latitude__gte=lat_min,
            latitude__lte=lat_max,
            longitude__gte=lon_min,
            longitude__lte=lon_max
        )
        
        # Exclude user if specified
        if exclude_user_id:
            queryset = queryset.exclude(user_id=exclude_user_id)
        
        # Create haversine distance calculation expressions
        lat_rad = math.radians(lat)
        
        # Calculate haversine components
        # Note: ExpressionWrapper is used to perform complex calculations in the ORM
        queryset = queryset.annotate(
            latitude_rad=ExpressionWrapper(
                models.functions.Radians(F('latitude')),
                output_field=FloatField()
            ),
            longitude_rad=ExpressionWrapper(
                models.functions.Radians(F('longitude')),
                output_field=FloatField()
            ),
            lon_diff=ExpressionWrapper(
                models.functions.Radians(F('longitude')) - models.Value(math.radians(lon)),
                output_field=FloatField()
            ),
            lat_diff=ExpressionWrapper(
                models.functions.Radians(F('latitude')) - models.Value(lat_rad),
                output_field=FloatField()
            ),
            a=ExpressionWrapper(
                models.functions.Sin(F('lat_diff')/2) * models.functions.Sin(F('lat_diff')/2) +
                models.functions.Cos(models.Value(lat_rad)) * models.functions.Cos(F('latitude_rad')) * 
                models.functions.Sin(F('lon_diff')/2) * models.functions.Sin(F('lon_diff')/2),
                output_field=FloatField()
            ),
            distance=ExpressionWrapper(
                2 * models.Value(R) * models.functions.ATan2(
                    models.functions.Sqrt(F('a')),
                    models.functions.Sqrt(1 - F('a'))
                ),
                output_field=FloatField()
            )
        )
        
        # Filter by exact distance and order by proximity
        return queryset.filter(distance__lte=max_distance_km).order_by('distance')


class Room(models.Model):
    """Model to store chat rooms"""
    room_id = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rooms')
    request_text = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Room {self.room_id} by {self.creator.name}"
    
    @property
    def members_count(self):
        return self.members.count()
    
    @property
    def member_list(self):
        """Return a list of user_ids in this room"""
        return list(self.members.values_list('user__user_id', flat=True))


class RoomMember(models.Model):
    """Model to store room membership"""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rooms')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('room', 'user')
        
    def __str__(self):
        return f"{self.user.name} in {self.room.room_id}"
