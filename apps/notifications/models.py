# notifications/models.py

from django.conf import settings
from django.db import models
from django.db import transaction
from django.db import models as django_models
from django.utils import timezone
from apps.companies.models import Company
from apps.emission.models import EmissionAssignment


# ====== NOTIFICATION MODEL ======
class Notification(models.Model):

    class ModuleChoices(models.TextChoices):
        EMISSION = "EMISSION", "Emission"
        GOALS = "GOALS", "Goals & KPI"
        QUESTIONS = "QUESTIONS", "Questions"
        BRSR = "BRSR", "BRSR"

    class NotificationTypeChoices(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        REMINDER = "REMINDER", "Reminder"
        OVERDUE = "OVERDUE", "Overdue"

    notification_code = models.CharField(
        max_length=20,
        unique=True,
        editable=False
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_notifications"
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_notifications"
    )

    module = models.CharField(
        max_length=30,
        choices=ModuleChoices.choices
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationTypeChoices.choices
    )

    title = models.CharField(
        max_length=255
    )

    message = models.TextField()

    reference_id = models.PositiveBigIntegerField(
        null=True,
        blank=True
    )

    action_url = models.CharField(
        max_length=500,
        blank=True,
        null=True
    )

    is_read = models.BooleanField(
        default=False
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_code} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.notification_code:
            with transaction.atomic():
                last_notification = (
                    Notification.objects
                    .select_for_update()
                    .order_by("-id")
                    .first()
                )

                if last_notification:
                    last_number = int(last_notification.notification_code.replace("NT", ""))
                    next_number = last_number + 1
                else:
                    next_number = 1

                self.notification_code = f"NT{next_number:06d}"

        super().save(*args, **kwargs)


# ====== TIMESHEET MODEL ======
class Timesheet(models.Model):
    """
    Timesheet model for tracking user work hours and assignments
    
    Status Flow:
    1. Assignment Created → assigned (Shows "New")
    2. User Clicks on Timesheet → viewed (Shows "Viewed")
    3. Assignment Submitted → completed (Shows "Completed")
    4. Due Date Passes → overdue (Shows "Overdue")
    5. Assignment Approved → completed (Shows "Completed")
    6. Assignment Rejected → rejected (Shows "Rejected")
    """
    
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('viewed', 'Viewed'),
        ('completed', 'Completed'),
        ('overdue', 'Overdue'),
        ('rejected', 'Rejected'),
    ]
    
    # ====== Relationships ======
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='timesheets',
        verbose_name='User'
    )
    
    assignment = models.ForeignKey(
        EmissionAssignment, 
        on_delete=models.CASCADE,
        related_name='timesheets',
        verbose_name='Assignment',
        null=True,
        blank=True
    )
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='timesheets',
        null=True,
        blank=True,
        verbose_name='Company'
    )
    
    # ====== Basic Fields ======
    title = models.CharField(
        max_length=200,
        verbose_name='Title'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Description'
    )
    
    # ====== Date Fields ======
    start_date = models.DateTimeField(
        verbose_name='Start Date'
    )
    
    end_date = models.DateTimeField(
        verbose_name='End Date'
    )
    
    # ====== Hours Worked ======
    hours_worked = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name='Hours Worked',
        help_text='Total hours worked for this timesheet'
    )
    
    # ====== Status ======
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='assigned',
        verbose_name='Status'
    )
    
    # ====== Timestamps ======
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Created At'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Updated At'
    )
    
    # ====== Tracking Fields ======
    viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Viewed At'
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Completed At'
    )
    
    # ====== Notification Reference ======
    notification = models.ForeignKey(
        Notification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timesheets',
        verbose_name='Related Notification'
    )
    
    # ====== Meta ======
    class Meta:
        db_table = "timesheets"
        ordering = ['-created_at']
        verbose_name = 'Timesheet'
        verbose_name_plural = 'Timesheets'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['created_at']),
            models.Index(fields=['company']),
        ]
    
    # ====== String Representation ======
    def __str__(self):
        return f"{self.title} - {self.user.get_full_name() or self.user.username}"
    
    # ====== Status Update Methods ======
    
    def mark_as_viewed(self):
        """
        Mark timesheet as viewed (User clicked on it)
        Status: assigned → viewed
        """
        if self.status == 'assigned':
            self.status = 'viewed'
            self.viewed_at = timezone.now()
            self.save(update_fields=['status', 'viewed_at'])
            return True
        return False
    
    def mark_as_completed(self):
        """
        Mark timesheet as completed (Assignment submitted or approved)
        Status: assigned/viewed/overdue → completed
        """
        if self.status in ['assigned', 'viewed', 'overdue']:
            self.status = 'completed'
            self.completed_at = timezone.now()
            self.save(update_fields=['status', 'completed_at'])
            return True
        return False
    
    def mark_as_overdue(self):
        """
        Mark timesheet as overdue (Due date passed)
        Status: assigned/viewed → overdue
        """
        if self.status in ['assigned', 'viewed']:
            self.status = 'overdue'
            self.save(update_fields=['status'])
            return True
        return False
    
    def mark_as_rejected(self):
        """
        Mark timesheet as rejected (Assignment rejected)
        Status: any → rejected
        """
        if self.status != 'rejected':
            self.status = 'rejected'
            self.save(update_fields=['status'])
            return True
        return False
    
    def check_and_update_overdue(self):
        """
        Check if timesheet is overdue and update status
        """
        if self.status in ['assigned', 'viewed'] and timezone.now() > self.end_date:
            self.mark_as_overdue()
            return True
        return False
    
    def update_status_from_assignment(self):
        """
        Update timesheet status based on assignment status and due date
        
        Flow:
        1. Assignment created → assigned (New)
        2. User clicks → viewed
        3. Assignment submitted → completed
        4. Due date passes → overdue
        5. Assignment approved → completed
        6. Assignment rejected → rejected
        """
        if not self.assignment:
            return False
        
        assignment = self.assignment
        status_changed = False
        
        if hasattr(assignment, 'status'):
            # 1. Check if assignment is APPROVED → Completed
            if assignment.status == 'APPROVED':
                if self.status != 'completed':
                    print(f"   ✅ Assignment APPROVED → Marking as completed")
                    self.mark_as_completed()
                    status_changed = True
            
            # 2. Check if assignment is REJECTED → Rejected
            elif assignment.status == 'REJECTED':
                if self.status != 'rejected':
                    print(f"   ✅ Assignment REJECTED → Marking as rejected")
                    self.mark_as_rejected()
                    status_changed = True
            
            # 3. Check if assignment is SUBMITTED → Completed
            elif assignment.status == 'SUBMITTED':
                if self.status not in ['completed', 'rejected']:
                    print(f"   ✅ Assignment SUBMITTED → Marking as completed")
                    self.mark_as_completed()
                    status_changed = True
            
            # 4. Check for overdue (only for ASSIGNED or IN_PROGRESS)
            elif assignment.status in ['ASSIGNED', 'IN_PROGRESS']:
                # Check if overdue
                if assignment.due_date and timezone.now().date() > assignment.due_date:
                    # Only mark as overdue if not already completed or rejected
                    if self.status not in ['completed', 'overdue', 'rejected']:
                        print(f"   ✅ Due date passed → Marking as overdue")
                        self.mark_as_overdue()
                        status_changed = True
                else:
                    # If not overdue and status is overdue, reset to assigned
                    if self.status == 'overdue':
                        print(f"   ✅ Not overdue anymore → Resetting to assigned")
                        self.status = 'assigned'
                        self.save(update_fields=['status'])
                        status_changed = True
        
        print(f"   Final timesheet status: {self.status}")
        return status_changed
    
    # ====== Helper Methods ======
    
    def get_status_color(self):
        """
        Get Bootstrap color class for status
        """
        status_colors = {
            'assigned': 'primary',
            'viewed': 'info',
            'completed': 'success',
            'overdue': 'danger',
            'rejected': 'danger',
        }
        return status_colors.get(self.status, 'secondary')
    
    def get_status_display(self):
        """
        Get display name for status
        """
        status_display = {
            'assigned': 'New',
            'viewed': 'Viewed',
            'completed': 'Completed',
            'overdue': 'Overdue',
            'rejected': 'Rejected',
        }
        return status_display.get(self.status, self.status.capitalize())
    
    def get_duration_days(self):
        """
        Get duration in days
        """
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            return delta.days
        return 0
    
    def is_unread(self):
        """
        Check if timesheet is unread (assigned or viewed)
        """
        return self.status in ['assigned', 'viewed']
    
    # ====== Class Methods ======
    
    @classmethod
    def get_unread_count_for_user(cls, user):
        """
        Get count of unread timesheets for a user (assigned and viewed only)
        """
        if not user:
            return 0
        return cls.objects.filter(
            django_models.Q(user=user) | django_models.Q(assignment__assignee=user)
        ).filter(
            django_models.Q(status='assigned') | django_models.Q(status='viewed')
        ).count()

    @classmethod
    def get_timesheets_for_user(cls, user, limit=10):
        """
        Get ALL timesheets for a user (including completed, overdue, rejected)
        """
        if not user:
            return cls.objects.none()
        return cls.objects.filter(
            django_models.Q(user=user) | django_models.Q(assignment__assignee=user)
        ).select_related('assignment', 'company', 'user').order_by('-created_at')[:limit]
    
    @classmethod
    def create_from_assignment(cls, assignment):
        """
        Create a timesheet from an assignment
        """
        if not assignment or not assignment.assignee:
            return None
        
        # Check if timesheet already exists
        existing = cls.objects.filter(assignment=assignment).first()
        if existing:
            return existing
        
        # Calculate dates
        start_date = assignment.created_at or timezone.now()
        end_date = assignment.due_date or (timezone.now() + timezone.timedelta(days=7))
        
        # Get title from assignment
        title = None
        if hasattr(assignment, 'title') and assignment.title:
            title = f"Timesheet: {assignment.title}"
        elif hasattr(assignment, 'name') and assignment.name:
            title = f"Timesheet: {assignment.name}"
        elif hasattr(assignment, 'scope') and assignment.scope and hasattr(assignment.scope, 'name'):
            title = f"Timesheet: {assignment.scope.name}"
        else:
            title = f"Assignment #{assignment.id}"
        
        # Get description
        description = None
        if hasattr(assignment, 'description') and assignment.description:
            description = assignment.description
        elif hasattr(assignment, 'scope') and assignment.scope and hasattr(assignment.scope, 'description'):
            description = assignment.scope.description
        else:
            description = f"Auto-created from assignment #{assignment.id}"
        
        # Create timesheet with 'assigned' status (New)
        timesheet = cls.objects.create(
            user=assignment.assignee,
            assignment=assignment,
            company=assignment.company,
            title=title,
            description=description,
            start_date=start_date,
            end_date=end_date,
            status='assigned',
            hours_worked=0
        )
        
        # Create notification
        try:
            notification = Notification.objects.create(
                company=assignment.company,
                sender=assignment.assigner or assignment.assignee,
                recipient=assignment.assignee,
                module=Notification.ModuleChoices.EMISSION,
                notification_type=Notification.NotificationTypeChoices.ASSIGNED,
                title=f"New Timesheet: {title}",
                message=f"A new timesheet has been created for assignment #{assignment.id}",
                reference_id=assignment.id,
                action_url=f"/emission/assignments/?assignment={assignment.id}",
                is_read=False
            )
            timesheet.notification = notification
            timesheet.save(update_fields=['notification'])
        except Exception as e:
            print(f"Error creating notification: {e}")
        
        return timesheet