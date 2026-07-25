# notifications/context_processors.py

from django.db import models
from .models import Timesheet, Notification

def global_notifications(request):
    """
    Context processor to add notifications and timesheets to all templates
    """
    if request.user.is_authenticated:
        try:
            # ====== GET ALL TIMESHEETS (including completed, overdue, rejected) ======
            timesheets = Timesheet.objects.filter(
                models.Q(user=request.user) | 
                models.Q(assignment__assignee=request.user)
            ).select_related('assignment', 'company', 'user').order_by('-created_at')[:10]
            
            # ====== COUNT ONLY UNREAD for the badge (assigned and viewed) ======
            timesheet_count = Timesheet.objects.filter(
                models.Q(user=request.user) | 
                models.Q(assignment__assignee=request.user)
            ).filter(
                models.Q(status='assigned') | models.Q(status='viewed')
            ).count()
            
            # ====== GET NOTIFICATIONS ======
            # Get ALL notifications (read and unread) for the dropdown
            navbar_notifications = Notification.objects.filter(
                recipient=request.user
            ).exclude(
                title__icontains='Timesheet'
            ).order_by('-created_at')[:10]
            
            # Count ONLY unread for the badge
            navbar_notification_count = Notification.objects.filter(
                recipient=request.user,
                is_read=False
            ).exclude(
                title__icontains='Timesheet'
            ).count()
            
            return {
                'timesheets': timesheets,
                'timesheet_count': timesheet_count,
                'navbar_notifications': navbar_notifications,
                'navbar_notification_count': navbar_notification_count,
            }
        except Exception as e:
            print(f"Error in global_notifications context processor: {e}")
    
    return {
        'timesheets': [],
        'timesheet_count': 0,
        'navbar_notifications': [],
        'navbar_notification_count': 0,
    }