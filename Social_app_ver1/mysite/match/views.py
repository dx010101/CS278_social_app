from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import UserProfile
import json
from django.http import JsonResponse

# Create your views here.

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('chat')
        else:
            return render(request, 'match/login.html', {'error': 'Invalid username or password'})
    
    return render(request, 'match/login.html')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if User.objects.filter(username=username).exists():
            return render(request, 'match/register.html', {'error': 'Username already exists'})
        
        user = User.objects.create_user(username=username, password=password)
        login(request, user)
        return redirect('chat')
    
    return render(request, 'match/register.html')

@login_required
def chat_view(request):
    return render(request, 'match/chat.html')

@login_required
def profile_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            profile = request.user.userprofile
            profile.interests = data.get('interests', [])
            profile.location = data.get('location', {"lat": 0, "lon": 0})
            profile.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return render(request, 'match/profile.html', {
        'profile': request.user.userprofile
    })

def logout_view(request):
    logout(request)
    return redirect('login')
