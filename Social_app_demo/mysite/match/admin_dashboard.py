from django.contrib import admin
from django.urls import path
from django.template.response import TemplateResponse
from django.db.models import Count, Avg
from .models import User

class UserDashboardView(admin.AdminSite):
    """Custom admin dashboard for user management"""
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('match/user-dashboard/', self.admin_view(self.user_dashboard_view), name='user-dashboard'),
        ]
        return custom_urls + urls
    
    def user_dashboard_view(self, request):
        """User dashboard view with analytics"""
        
        # Basic stats
        total_users = User.objects.count()
        
        # Users by major
        users_by_major = User.objects.values('major').annotate(
            count=Count('id')
        ).order_by('-count')[:5]  # Top 5 majors
        
        # Users by hometown
        users_by_hometown = User.objects.values('hometown').annotate(
            count=Count('id')
        ).order_by('-count')[:5]  # Top 5 hometowns
        
        # Average interest count
        avg_interests = User.objects.annotate(
            interest_count=Count('interests')
        ).aggregate(avg=Avg('interest_count'))['avg'] or 0
        
        # Most common interests
        # This is a bit complex with JSONField, so we'll simulate it
        interest_counts = {}
        for user in User.objects.all():
            for interest in user.interests:
                interest_counts[interest] = interest_counts.get(interest, 0) + 1
                
        # Convert to list and sort
        common_interests = [
            {'name': k, 'count': v} 
            for k, v in interest_counts.items()
        ]
        common_interests.sort(key=lambda x: x['count'], reverse=True)
        common_interests = common_interests[:10]  # Top 10
        
        context = {
            'title': 'User Dashboard',
            'total_users': total_users,
            'users_by_major': users_by_major,
            'users_by_hometown': users_by_hometown,
            'avg_interests': round(avg_interests, 1),
            'common_interests': common_interests,
            **admin.site.each_context(request),
        }
        
        return TemplateResponse(request, "admin/match/user_dashboard.html", context)

# Register the dashboard view
user_dashboard = UserDashboardView() 