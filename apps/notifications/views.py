from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
import json
from apps.accounts.mixins import SuperAdminRequiredMixin
from .models import Notification,Timesheet


class NotificationListView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "applications/notification_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Notification Master"
        context["notifications"] = (
            Notification.objects
            .filter(recipient=self.request.user)
            .select_related("sender", "company")
            .order_by("-created_at")
        )
        return context


# Add these new functions
@login_required
@csrf_exempt
def mark_notification_as_read(request, notification_id):
    """Mark a single notification as read"""
    if request.method == 'POST':
        try:
            notification = get_object_or_404(
                Notification,
                id=notification_id,
                recipient=request.user
            )
            notification.is_read = True
            notification.read_at = timezone.now()  # Assuming you have this field
            notification.save()
            return JsonResponse({'success': True})
        except Notification.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)


@login_required
@csrf_exempt
def mark_all_notifications_as_read(request):
    """Mark all notifications as read for the current user"""
    if request.method == 'POST':
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return JsonResponse({'success': True, 'count': count})
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
@login_required
@csrf_exempt
def mark_timesheet_viewed(request, timesheet_id):
    """
    API endpoint to mark a timesheet as viewed
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        timesheet = Timesheet.objects.get(id=timesheet_id)
        
        # Check if user has permission (is the owner or assignee)
        if timesheet.user != request.user and timesheet.assignment.assignee != request.user:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Mark as viewed
        timesheet.mark_as_viewed()
        
        return JsonResponse({
            'success': True,
            'message': 'Timesheet marked as viewed'
        })
        
    except Timesheet.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Timesheet not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
def mark_all_timesheets_viewed(request):
    """
    API endpoint to mark all timesheets as viewed
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        timesheet_ids = data.get('timesheet_ids', [])
        
        if not timesheet_ids:
            return JsonResponse({'success': False, 'error': 'No timesheet IDs provided'}, status=400)
        
        # Mark all as viewed
        timesheets = Timesheet.objects.filter(
            id__in=timesheet_ids,
            user=request.user
        )
        
        updated_count = 0
        for timesheet in timesheets:
            timesheet.mark_as_viewed()
            updated_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'{updated_count} timesheets marked as viewed'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)