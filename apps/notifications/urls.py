from django.urls import path

from .views import NotificationListView
from .api_views import NotificationListAPIView
from . import views  # Add this import

app_name = "notifications"

urlpatterns = [
    path("notification_list/", NotificationListView.as_view(), name="notification_list"),
    path("api/list/", NotificationListAPIView.as_view(), name="notification-list"),
    # Add these two new URLs
    path("mark-read/<int:notification_id>/", views.mark_notification_as_read, name="mark_notification_read"),
    path("mark-all-read/", views.mark_all_notifications_as_read, name="mark_all_read"),
    path('api/timesheets/mark-viewed/<int:timesheet_id>/', 
         views.mark_timesheet_viewed, 
         name='mark_timesheet_viewed'),
    
    path('api/timesheets/mark-all-viewed/', 
         views.mark_all_timesheets_viewed, 
         name='mark_all_timesheets_viewed'),
]