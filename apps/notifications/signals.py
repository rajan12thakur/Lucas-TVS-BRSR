# notifications/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from apps.emission.models import EmissionAssignment
from .models import Timesheet, Notification


@receiver(post_save, sender=EmissionAssignment)
def create_timesheet_from_assignment(sender, instance, created, **kwargs):
    """
    Auto-create a timesheet when an assignment is created
    """
    if created and instance.assignee:
        # Calculate duration (default to 7 days if no due date)
        end_date = instance.due_date if instance.due_date else instance.created_at + timezone.timedelta(days=7)
        
        # Check if timesheet already exists
        existing_timesheet = Timesheet.objects.filter(assignment=instance).first()
        if existing_timesheet:
            print(f"⚠️ Timesheet already exists for assignment {instance.id}")
            return
        
        # Get title
        title = None
        if hasattr(instance, 'title') and instance.title:
            title = f"Timesheet: {instance.title}"
        elif hasattr(instance, 'name') and instance.name:
            title = f"Timesheet: {instance.name}"
        elif hasattr(instance, 'scope') and instance.scope and hasattr(instance.scope, 'name'):
            title = f"Timesheet: {instance.scope.name}"
        else:
            title = f"Assignment #{instance.id}"
        
        # Create timesheet with 'assigned' status (New)
        timesheet = Timesheet.objects.create(
            user=instance.assignee,
            assignment=instance,
            company=instance.company,
            title=title,
            description=f"Auto-created from assignment #{instance.id}",
            start_date=instance.created_at,
            end_date=end_date,
            status='assigned',  # New status
            hours_worked=0
        )
        
        # Create notification for the timesheet
        try:
            notification = Notification.objects.create(
                company=instance.company,
                sender=instance.assigner or instance.assignee,
                recipient=instance.assignee,
                module=Notification.ModuleChoices.EMISSION,
                notification_type=Notification.NotificationTypeChoices.ASSIGNED,
                title=f'New Timesheet: {title}',
                message=f'You have been assigned a new timesheet. Please review it.',
                reference_id=instance.id,
                action_url=f'/emission/assignments/?assignment={instance.id}',
                is_read=False
            )
            timesheet.notification = notification
            timesheet.save(update_fields=['notification'])
        except Exception as e:
            print(f"Error creating notification for timesheet: {e}")
        
        print(f"✅ Timesheet created for assignment {instance.id}: {timesheet.title} (Status: {timesheet.status})")


@receiver(post_save, sender=EmissionAssignment)
def update_timesheet_on_assignment_update(sender, instance, created, **kwargs):
    """
    Update timesheet when assignment is updated (status change, dates, etc.)
    """
    if not created and instance.assignee:
        try:
            timesheet = Timesheet.objects.get(assignment=instance)
            
            # Update title if changed
            if hasattr(instance, 'title') and instance.title:
                timesheet.title = f"Timesheet: {instance.title}"
            elif hasattr(instance, 'name') and instance.name:
                timesheet.title = f"Timesheet: {instance.name}"
            
            # Update dates if changed
            if instance.due_date:
                timesheet.end_date = instance.due_date
            
            # Update status based on assignment
            print(f"\n📝 Updating timesheet for assignment {instance.id}")
            timesheet.update_status_from_assignment()
            
            timesheet.save()
            print(f"✅ Timesheet updated for assignment {instance.id}\n")
            
        except Timesheet.DoesNotExist:
            # If timesheet doesn't exist but assignment updated, create one
            if instance.assignee:
                print(f"⚠️ Timesheet not found for assignment {instance.id}, creating one...")
                create_timesheet_from_assignment(sender, instance, created=False, **kwargs)
        except Exception as e:
            print(f"❌ Error updating timesheet for assignment {instance.id}: {e}")


@receiver(post_save, sender=Timesheet)
def update_assignment_on_timesheet_completion(sender, instance, created, **kwargs):
    """
    Update assignment when timesheet is completed (optional)
    """
    if not created and instance.status == 'completed' and instance.assignment:
        try:
            # If timesheet is marked as completed, you might want to update assignment
            # This is optional - uncomment if needed
            # if instance.assignment.status not in ['APPROVED', 'REJECTED']:
            #     instance.assignment.status = 'SUBMITTED'
            #     instance.assignment.save(update_fields=['status'])
            print(f"✅ Timesheet {instance.id} completed for assignment {instance.assignment.id}")
        except Exception as e:
            print(f"❌ Error updating assignment: {e}")