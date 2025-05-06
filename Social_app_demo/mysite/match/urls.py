from django.urls import path
from . import views

app_name = 'match'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('profile/', views.profile_view, name='profile'),
    path('nearby/', views.nearby_view, name='nearby'),
] 