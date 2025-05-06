from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from .models import User, Room, RoomMember
from . import admin_dashboard

# Register your models here.
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'name', 'major', 'hometown', 'get_interests', 'location_display', 'created_at')
    list_filter = ('major', 'hometown', 'created_at')
    search_fields = ('user_id', 'name', 'hometown', 'major', 'interests')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user_id', 'name', 'interests')
        }),
        ('Academic Information', {
            'fields': ('major', 'hometown')
        }),
        ('Location Data', {
            'fields': ('latitude', 'longitude'),
            'description': 'Geographic coordinates used for proximity matching'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_interests(self, obj):
        """Display interests as a comma-separated list"""
        if not obj.interests:
            return "-"
        return ", ".join(obj.interests)
    get_interests.short_description = 'Interests'
    
    def location_display(self, obj):
        """Display latitude and longitude in a readable format"""
        return f"{obj.latitude:.4f}, {obj.longitude:.4f}"
    location_display.short_description = 'Location'
    
    actions = ['export_selected_users']
    
    def export_selected_users(self, request, queryset):
        """Custom admin action to export selected users"""
        # In a real application, this would generate a CSV or similar export file
        self.message_user(request, f"{queryset.count()} users have been exported.")
    export_selected_users.short_description = "Export selected users"
    
    # Custom view for the changelist page
    def changelist_view(self, request, extra_context=None):
        """Add extra context to the changelist view"""
        extra_context = extra_context or {}
        extra_context['total_users'] = User.objects.count()
        return super().changelist_view(request, extra_context=extra_context)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_site.admin_view(self.dashboard_redirect), name='user-dashboard-redirect'),
        ]
        return custom_urls + urls
    
    def dashboard_redirect(self, request):
        return redirect('admin:user-dashboard')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'creator', 'members_count', 'active', 'created_at')
    list_filter = ('active', 'created_at')
    search_fields = ('room_id', 'creator__name', 'creator__user_id', 'request_text')
    readonly_fields = ('created_at', 'updated_at', 'get_members')
    
    fieldsets = (
        ('Room Information', {
            'fields': ('room_id', 'creator', 'request_text', 'active')
        }),
        ('Members', {
            'fields': ('get_members',),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_members(self, obj):
        """Display room members as a list"""
        members = obj.members.select_related('user').all()
        if not members:
            return "No members"
        
        return ", ".join([f"{m.user.name} ({m.user.user_id})" for m in members])
    get_members.short_description = 'Room Members'
    
    def members_count(self, obj):
        """Display number of members in the room"""
        return obj.members.count()
    members_count.short_description = 'Members'


@admin.register(RoomMember)
class RoomMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'is_active', 'joined_at')
    list_filter = ('is_active', 'joined_at')
    search_fields = ('user__name', 'user__user_id', 'room__room_id')
    readonly_fields = ('joined_at',)


# Add custom admin views by extending AdminSite's get_urls
# The original way was trying to use a non-existent 'register_view' method
# Let's use the correct approach to add custom admin URLs

# Create a function to get custom admin URLs
def get_admin_urls(urls):
    # Add custom URL patterns
    custom_urls = [
        path('match/user-dashboard/', 
             admin.site.admin_view(admin_dashboard.user_dashboard.user_dashboard_view), 
             name='user-dashboard'),
    ]
    
    # Return the combined URL patterns
    return custom_urls + urls

# Store the original get_urls method
original_get_urls = admin.site.get_urls

# Create a new get_urls method that adds our custom URLs
def custom_get_urls():
    return get_admin_urls(original_get_urls())

# Replace the get_urls method with our custom version
admin.site.get_urls = custom_get_urls
