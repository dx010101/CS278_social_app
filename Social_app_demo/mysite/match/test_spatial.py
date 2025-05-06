import os
import sys
import time
import random
import math
import django

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()

# Import User model
from match.models import User

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in kilometers."""
    R = 6371  # Earth radius in kilometers
    
    # Convert latitude and longitude from degrees to radians
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance

def test_spatial_efficiency():
    """Test the efficiency of our spatial query implementation."""
    print("Testing spatial query efficiency...")
    
    # Create test data if needed
    if User.objects.count() < 200:
        print('Creating test data...')
        for i in range(200):
            # Create random users around San Francisco
            lat = 37.7749 + (random.random() - 0.5) * 2  # +/- 1 degree
            lon = -122.4194 + (random.random() - 0.5) * 2
            
            try:
                User.objects.get_or_create(
                    user_id=f'test{i}',
                    defaults={
                        'name': f'Test User {i}',
                        'interests': ['test'],
                        'hometown': 'Test City',
                        'major': 'Test Major',
                        'latitude': lat,
                        'longitude': lon
                    }
                )
            except Exception as e:
                print(f"Error creating test user {i}: {e}")
        
        print(f'Created test users. Total users: {User.objects.count()}')
    
    # SF coordinates
    test_center = (37.7749, -122.4194)
    
    # Test for various radii
    for radius in [1, 5, 10, 50]:
        print(f"\n--- Testing with radius {radius}km ---")
        
        # Method 1: Our optimized approach
        start_time = time.time()
        nearby_users = User.nearby_users(
            lat=test_center[0],
            lon=test_center[1],
            max_distance_km=radius
        )
        optimized_time = time.time() - start_time
        
        # Method 2: Naive approach - calculate distance for all users
        start_time = time.time()
        all_users = list(User.objects.all())
        naive_users = []
        
        for user in all_users:
            dist = haversine(
                test_center[0], test_center[1],
                user.latitude, user.longitude
            )
            if dist <= radius:
                user.distance = dist
                naive_users.append(user)
        
        naive_users.sort(key=lambda u: u.distance)
        naive_time = time.time() - start_time
        
        # Results
        print(f"Optimized method: Found {len(nearby_users)} users in {optimized_time:.6f} seconds")
        print(f"Naive method: Found {len(naive_users)} users in {naive_time:.6f} seconds")
        
        if len(naive_users) > 0 and len(nearby_users) > 0:
            speedup = naive_time / optimized_time
            print(f"Speedup factor: {speedup:.2f}x")
            
            # Verify results match
            nearby_ids = set(u.user_id for u in nearby_users)
            naive_ids = set(u.user_id for u in naive_users)
            
            if nearby_ids == naive_ids:
                print("✓ Both methods returned the same users")
            else:
                print("✗ Results differ between methods")
                print(f"Users in naive but not in optimized: {len(naive_ids - nearby_ids)}")
                print(f"Users in optimized but not in naive: {len(nearby_ids - naive_ids)}")

if __name__ == "__main__":
    test_spatial_efficiency() 