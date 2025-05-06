from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from .models import User
import json

# Create your views here.

def home_view(request):
    """Simple home view that redirects to profile"""
    return redirect('match:profile')

@login_required
def profile_view(request):
    """
    View to display and edit user profile information.
    
    For simplicity in our demo, we'll use the Django auth username as the user_id.
    In a real application, you might have a more complex user mapping system.
    """
    # Get user_id from Django auth system (in a real app, you'd have proper integration)
    user_id = request.user.username
    
    # Try to get the user's profile, or create a default one if it doesn't exist
    try:
        user_profile = User.objects.get(user_id=user_id)
    except User.DoesNotExist:
        # Create a new profile with default values
        user_profile = User(
            user_id=user_id,
            name=request.user.get_full_name() or user_id,
            interests=[],
            hometown="",
            major="",
            latitude=37.7749, # Default to San Francisco
            longitude=-122.4194
        )
        user_profile.save()
    
    if request.method == 'POST':
        # Handle profile update
        try:
            # Get form data
            name = request.POST.get('name')
            hometown = request.POST.get('hometown')
            major = request.POST.get('major')
            
            # Handle interests (convert comma-separated string to list)
            interests_str = request.POST.get('interests', '')
            interests = [i.strip() for i in interests_str.split(',') if i.strip()]
            
            # Get location data
            latitude = float(request.POST.get('latitude'))
            longitude = float(request.POST.get('longitude'))
            
            # Update user profile
            user_profile.name = name
            user_profile.hometown = hometown
            user_profile.major = major
            user_profile.interests = interests
            user_profile.latitude = latitude
            user_profile.longitude = longitude
            user_profile.save()
            
            # Add a success message to context
            return render(request, 'match/profile.html', {
                'user': user_profile,
                'success_message': 'Profile updated successfully!'
            })
            
        except Exception as e:
            # Return with error
            return render(request, 'match/profile.html', {
                'user': user_profile,
                'error_message': f'Error updating profile: {str(e)}'
            })
    
    # For GET request or after post, display the profile
    return render(request, 'match/profile.html', {'user': user_profile})

@login_required
def nearby_view(request):
    """
    View to display nearby users based on current user's location.
    """
    # Get current user
    user_id = request.user.username
    
    try:
        current_user = User.objects.get(user_id=user_id)
        
        # Get maximum distance (default 5km)
        max_distance = float(request.GET.get('distance', 5))
        
        # Get nearby users
        nearby_users = User.nearby_users(
            current_user.latitude,
            current_user.longitude,
            max_distance,
            exclude_user_id=user_id
        )
        
        return render(request, 'match/nearby.html', {
            'current_user': current_user,
            'nearby_users': nearby_users,
            'max_distance': max_distance
        })
        
    except User.DoesNotExist:
        # Redirect to profile if user doesn't exist
        return redirect('match:profile')
