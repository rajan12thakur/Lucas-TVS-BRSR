# notifications/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Notification, Timesheet


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "notification_code",
        "title",
        "recipient",
        "sender",
        "module",
        "notification_type",
        "is_read",
        "created_at",
    )

    list_filter = (
        "module",
        "notification_type",
        "is_read",
        "created_at",
    )

    search_fields = (
        "notification_code",
        "title",
        "message",
        "recipient__username",
        "recipient__first_name",
        "recipient__last_name",
        "sender__username",
        "sender__first_name",
        "sender__last_name",
    )

    readonly_fields = (
        "notification_code",
        "created_at",
        "read_at",
    )

    ordering = (
        "-created_at",
    )

    date_hierarchy = "created_at"

    list_per_page = 25

    autocomplete_fields = (
        "company",
        "sender",
        "recipient",
    )

    fieldsets = (
        (
            "Notification Information",
            {
                "fields": (
                    "notification_code",
                    "company",
                    "module",
                    "notification_type",
                    "title",
                    "message",
                    "reference_id",
                    "action_url",
                )
            },
        ),
        (
            "Users",
            {
                "fields": (
                    "sender",
                    "recipient",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_read",
                    "read_at",
                    "created_at",
                )
            },
        ),
    )


@admin.register(Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    """
    Admin configuration for Timesheet model
    """
    
    list_display = (
        "title",
        "user",
        "status_badge",
        "start_date",
        "end_date",
        "hours_worked",
        "created_at",
    )
    
    list_filter = (
        "status",
        "user",
        "company",
        "created_at",
    )
    
    search_fields = (
        "title",
        "description",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    
    readonly_fields = (
        "created_at",
        "updated_at",
        "viewed_at",
        "completed_at",
    )
    
    ordering = (
        "-created_at",
    )
    
    date_hierarchy = "created_at"
    
    list_per_page = 25
    
    # REMOVE assignment from autocomplete_fields to fix the error
    autocomplete_fields = (
        "user",
        "company",
        "notification",
    )
    
    # Use raw_id_fields for assignment (this avoids the autocomplete error)
    raw_id_fields = (
        "assignment",
    )
    
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "user",
                    "company",
                    "assignment",
                    "title",
                    "description",
                )
            },
        ),
        (
            "Date & Time",
            {
                "fields": (
                    "start_date",
                    "end_date",
                    "hours_worked",
                )
            },
        ),
        (
            "Status Tracking",
            {
                "fields": (
                    "status",
                    "viewed_at",
                    "completed_at",
                )
            },
        ),
        (
            "References",
            {
                "fields": (
                    "notification",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )
    
    def status_badge(self, obj):
        """Display status with color badge and icon"""
        status_config = {
            'assigned': {
                'color': 'primary',
                'icon': 'fa-tasks',
                'label': 'Assigned'
            },
            'viewed': {
                'color': 'info',
                'icon': 'fa-eye',
                'label': 'Viewed'
            },
            'completed': {
                'color': 'success',
                'icon': 'fa-check-circle',
                'label': 'Completed'
            },
            'overdue': {
                'color': 'danger',
                'icon': 'fa-exclamation-triangle',
                'label': 'Overdue'
            },
        }
        
        config = status_config.get(obj.status, {
            'color': 'secondary',
            'icon': 'fa-clock',
            'label': obj.get_status_display()
        })
        
        return format_html(
            '<span class="badge bg-{}"><i class="fas {}"></i> {}</span>',
            config['color'],
            config['icon'],
            config['label']
        )
    status_badge.short_description = 'Status'
    
    def progress_bar(self, obj):
        """Display progress bar based on status"""
        progress_map = {
            'assigned': 0,
            'viewed': 33,
            'completed': 100,
            'overdue': 0,
        }
        progress = progress_map.get(obj.status, 0)
        
        color_map = {
            'assigned': 'primary',
            'viewed': 'info',
            'completed': 'success',
            'overdue': 'danger',
        }
        color = color_map.get(obj.status, 'secondary')
        
        return format_html(
            '<div class="progress" style="width: 100px; height: 6px;">'
            '<div class="progress-bar bg-{}" role="progressbar" style="width: {}%;" '
            'aria-valuenow="{}" aria-valuemin="0" aria-valuemax="100"></div>'
            '</div>',
            color,
            progress,
            progress
        )
    progress_bar.short_description = 'Progress'
    
    def is_overdue(self, obj):
        """Check if timesheet is overdue"""
        if obj.status in ['assigned', 'viewed'] and timezone.now() > obj.end_date:
            return format_html('<span class="badge bg-danger">Yes</span>')
        return format_html('<span class="badge bg-success">No</span>')
    is_overdue.short_description = 'Overdue'
    is_overdue.boolean = True
    
    def duration_days(self, obj):
        """Get duration in days"""
        return obj.get_duration_days()
    duration_days.short_description = 'Duration (Days)'
    
    actions = [
        'mark_as_viewed', 
        'mark_as_completed', 
        'check_overdue',
    ]
    
    def mark_as_viewed(self, request, queryset):
        """Mark selected timesheets as viewed"""
        count = 0
        for timesheet in queryset:
            if timesheet.mark_as_viewed():
                count += 1
        self.message_user(request, f'{count} timesheets marked as viewed.')
    mark_as_viewed.short_description = 'Mark as viewed'
    
    def mark_as_completed(self, request, queryset):
        """Mark selected timesheets as completed"""
        count = 0
        for timesheet in queryset:
            if timesheet.mark_as_completed():
                count += 1
        self.message_user(request, f'{count} timesheets marked as completed.')
    mark_as_completed.short_description = 'Mark as completed'
    
    def check_overdue(self, request, queryset):
        """Check and update overdue status for selected timesheets"""
        count = 0
        for timesheet in queryset:
            if timesheet.check_and_update_overdue():
                count += 1
        self.message_user(request, f'{count} timesheets marked as overdue.')
    check_overdue.short_description = 'Check overdue status'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        return super().get_queryset(request).select_related(
            'user', 
            'company', 
            'assignment', 
            'notification'
        )
    
    def save_model(self, request, obj, form, change):
        """Override save to handle status changes"""
        if not change:  # New object
            obj.user = request.user
        super().save_model(request, obj, form, change)
        
        # Check if overdue after save
        if obj.status in ['assigned', 'viewed']:
            obj.check_and_update_overdue()