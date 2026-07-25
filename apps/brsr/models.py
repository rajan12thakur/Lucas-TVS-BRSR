"""
BRSR Principle Flow — Models
=========================================

Design goals addressed:
  1. Single source of truth for answers.
  2. One reusable workflow (draft -> submit -> approve/reject -> resubmit).
  3. Generic actor references (GenericForeignKey) so "who assigned / who
     answered / who reviewed" works for User, BusinessUnitStaff,
     LocationHead, PlantEmployee, etc. without new FK columns per model.
  4. One Assignment model (self-referencing) replacing QuestionAssignment
     + HODQuestionAssignment. Client -> HOD and HOD -> Employee are the
     same table, linked via `parent`.
  5. Sections are data (BRSRSection), not hardcoded choices, so new BRSR
     formats/years don't need a migration.
  6. Versioned questions, so a question can change wording/options across
     financial years without corrupting historical responses.

"""

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.text import slugify
from apps.organizations.workflow_configuration_engine import WorkflowConfigurationEngine
import os


# ---------------------------------------------------------------------------
# 1. Reusable workflow mixin
# ---------------------------------------------------------------------------

class WorkflowStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SUBMITTED = 'submitted', 'Submitted for Review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    RESUBMITTED = 'resubmitted', 'Resubmitted'


class WorkflowMixin(models.Model):
    """
    Mix into any model that needs draft -> submit -> approve/reject ->
    resubmit. Keeps status semantics identical everywhere instead of each
    model re-declaring its own status choices + reviewer fields.

    """
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    submitted_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_remark = models.TextField(blank=True, null=True)
    resubmission_count = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True

    def submit(self, user):
        self.status = (
            WorkflowStatus.RESUBMITTED if self.resubmission_count else WorkflowStatus.SUBMITTED
        )
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_by', 'submitted_at'])

    def approve(self, user, remark=''):
        self.status = WorkflowStatus.APPROVED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_remark = remark
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_remark'])

    def reject(self, user, remark):
        self.status = WorkflowStatus.REJECTED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_remark = remark
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_remark'])

    def resubmit(self, user):
        self.resubmission_count += 1
        self.submit(user)

    @property
    def is_editable(self):
        """Draft, rejected -> editable. Submitted/approved -> locked."""
        return self.status in (WorkflowStatus.DRAFT, WorkflowStatus.REJECTED)


# ---------------------------------------------------------------------------
# 2. Generic actor mixin (assignee / assigner / answered_by / etc.)
# ---------------------------------------------------------------------------

class ActorRefMixin(models.Model):
    """
    A single generic reference to 'whoever did this' — User, BusinessUnitStaff,
    LocationHead, PlantEmployee, BranchEmployee — without new FK columns
    every time a new actor type shows up. Subclass and rename the field
    trio per use (see Assignment.assignee / QuestionResponse.answered_by).
    """
    actor_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name='+'
    )
    actor_object_id = models.PositiveIntegerField()
    actor = GenericForeignKey('actor_content_type', 'actor_object_id')

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# 3. Principles & Sections
# ---------------------------------------------------------------------------

class BRSRSection(models.Model):
    """
    Replaces hardcoded section_a/section_b/section_c choices. New BRSR
    formats (e.g. a future 'Section D') are just a new row, not a migration.
    """
    code = models.SlugField(max_length=20, unique=True)   # 'section_a'
    name = models.CharField(max_length=100)                # 'General Disclosures'
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'code']

    def __str__(self):
        return self.name


class BRSRPrinciple(models.Model):

    principle_number = models.PositiveSmallIntegerField(unique=True)
    principle_name = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    img = models.ImageField(upload_to='brsr_principles/', blank=True, null=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['principle_name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.principle_name)
        original_slug, counter = self.slug, 1
        while BRSRPrinciple.objects.filter(slug=self.slug).exclude(id=self.id).exists():
            self.slug = f'{original_slug}-{counter}'
            counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.principle_name


# ---------------------------------------------------------------------------
# 4. Questions (versioned, dynamic sections)
# ---------------------------------------------------------------------------

class BRSRQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('text', 'Text Input'),
        ('textarea', 'Long Text'),
        ('number', 'Number'),
        ('decimal', 'Decimal'),
        ('currency', 'Currency'),
        ('percentage', 'Percentage'),
        ('year', 'Year'),
        ('email', 'Email'),
        ('url', 'URL'),
        ('phone', 'Phone'),
        ('date', 'Date'),
        ('dropdown', 'Dropdown'),
        ('select', 'Dropdown'),
        ('multi_select', 'Multi Select'),
        ('radio', 'Radio Button'),
        ('yes_no', 'Yes / No'),
        ('checkbox', 'Checkbox'),
        ('file', 'File Upload'),
        ('table', 'Table Data'),
        ('nested_table', 'Nested Table'),
        ('matrix', 'Matrix'),
        ('repeating_section', 'Repeating Section'),
        ('custom_component', 'Custom Component'),
    ]

    question_id = models.CharField(max_length=50, unique=True)  # 'a_q1', 'c_p1_q1'
    section = models.ForeignKey(BRSRSection, on_delete=models.PROTECT, related_name='questions')
    principle = models.ForeignKey(
        BRSRPrinciple, on_delete=models.CASCADE, null=True, blank=True, related_name='questions'
    )

    question_text = models.TextField()
    question_number = models.CharField(max_length=10)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)

    is_required = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    help_text = models.TextField(blank=True, null=True)
    placeholder_text = models.CharField(max_length=255, blank=True, null=True)
    options = models.JSONField(default=list, blank=True)
    validation_rules = models.JSONField(default=dict, blank=True)

    sub_section = models.CharField(max_length=100, blank=True, null=True)
    parent_question = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='superseded_by'
    )
    effective_from = models.CharField(max_length=20, blank=True, null=True)  # e.g. '2024-2025'
    effective_to = models.CharField(max_length=20, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['section', 'principle', 'display_order']
        unique_together = ('section', 'principle', 'question_number', 'sub_section', 'version')
        indexes = [
            models.Index(fields=['section', 'is_active']),
            models.Index(fields=['principle', 'is_active']),
        ]

    def __str__(self):
        p = f' - {self.principle.principle_name}' if self.principle else ''
        return f'{self.section.name}{p} - Q{self.question_number}: {self.question_text[:50]}'


# ---------------------------------------------------------------------------
# 5. Assignment of the questions
# ---------------------------------------------------------------------------

class Assignment(models.Model):
    """
    Self-referencing so any depth of delegation works with ONE table:
      Client -> HOD           (parent = null)
      HOD    -> Employee      (parent = the Client->HOD assignment)
      Employee -> sub-task    (parent = the HOD->Employee assignment, if ever needed)

    assigner / assignee are generic (User, BusinessUnitStaff, LocationHead,
    PlantEmployee, BranchEmployee) so adding a new actor role never
    requires a new FK column or a new near-duplicate model.
    """
    PRIORITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')]

    assignment_id = models.CharField(max_length=50, unique=True, blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='children'
    )

    plant = models.ForeignKey('organizations.Plant', on_delete=models.CASCADE, related_name='assignments')
    principle = models.ForeignKey(BRSRPrinciple, on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)
    section = models.ForeignKey(BRSRSection, on_delete=models.CASCADE, related_name='assignments')
    financial_year = models.CharField(max_length=20)
    workflow_template = models.ForeignKey(
        'organizations.ApprovalConfigurationTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='brsr_assignments',
    )

    questions = models.ManyToManyField(BRSRQuestion, related_name='assignments')
    workflow_tasks = GenericRelation(
        'organizations.ApprovalConfigurationTask',
        content_type_field='target_content_type',
        object_id_field='target_object_id',
        related_query_name='brsr_assignment',
    )

    # who assigned it (generic: User for client-level, BusinessUnitStaff for HOD-level, ...)
    assigner_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    assigner_object_id = models.PositiveIntegerField()
    assigner = GenericForeignKey('assigner_content_type', 'assigner_object_id')

    # who it's assigned to (generic)
    assignee_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    assignee_object_id = models.PositiveIntegerField()
    assignee = GenericForeignKey('assignee_content_type', 'assignee_object_id')

    # data collection
    FREQUENCY_CHOICES = [
        ('weekly', 'Weekly'), ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'), ('annually', 'Annually'),
    ]
    data_collection_frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, null=True, blank=True
    )
    selected_months = models.JSONField(default=list, blank=True)
    selected_quarters = models.JSONField(default=list, blank=True)

    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    notes = models.TextField(blank=True, null=True)
    assignment_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("in_progress", "In Progress"),
            ("rejected", "Rejected"),
            ("reassigned", "Reassigned"),
            ("approved", "Approved"),
        ],
        default="pending",
    )
    schedule = models.ForeignKey(
        'AssignmentSchedule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_assignments',
        help_text="Set when this Assignment was auto-generated by a recurring schedule.",
    )
    period_code = models.CharField(
        max_length=30, blank=True, null=True,
        help_text="e.g. 'APR', 'Q1', 'ANNUAL', 'Week-15' — identifies which recurrence period this is.",
    )
    period_label = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['assignee_content_type', 'assignee_object_id']),
            models.Index(fields=['plant', 'financial_year']),
            models.Index(fields=['parent']),
            ]
        constraints = [
            models.UniqueConstraint(
                fields=['schedule', 'financial_year', 'period_code'],
                condition=models.Q(schedule__isnull=False),
                name='uniq_scheduled_assignment_period',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.assignment_id:
            branch_code = self.plant.name[:3].upper() if self.plant_id else 'ASG'
            year = timezone.now().year
            count = Assignment.objects.filter(created_at__year=year).count() + 1
            self.assignment_id = f'{branch_code}-{year}-{count:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.assignment_id} -> {self.assignee}'

    @property
    def workflow_task(self):
        return self.workflow_tasks.select_related('template', 'current_stage').order_by('-created_at').first()

    @property
    def workflow_stage(self):
        task = self.workflow_task
        return task.current_stage if task else None

    @property
    def workflow_stage_label(self):
        stage = self.workflow_stage
        return stage.label if stage else ''

    @property
    def workflow_stage_type(self):
        stage = self.workflow_stage
        return stage.stage_type if stage else ''

    @property
    def is_editable(self):
        if self.assignment_status in {"rejected", "reassigned", "pending"}:
            return True
        stage_type = self.workflow_stage_type
        if stage_type:
            return stage_type == "data_entry"
        return True

    @property
    def workflow_template_name(self):
        return self.workflow_template.name if self.workflow_template_id else ''

    @property
    def is_overdue(self):
        return (self.due_date and self.due_date < timezone.now().date() and self.overall_status not in ("submitted", "completed"))

    @property
    def overall_status(self):
        """Roll up completion from child responses instead of a synced field."""
        if self.assignment_status == "approved":
            return "completed"
        if self.assignment_status in {"rejected", "reassigned", "in_progress", "pending"}:
            return self.assignment_status
        statuses = set(self.responses.values_list('status', flat=True))
        if not statuses:
            return 'pending'
        if statuses <= {WorkflowStatus.APPROVED}:
            return 'completed'
        if WorkflowStatus.REJECTED in statuses:
            return 'needs_revision'
        return 'in_progress'


class AssignmentReviewer(models.Model):
    """Through-table for reviewers, since M2M can't point at a GenericForeignKey directly."""
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='reviewer_links')
    reviewer_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    reviewer_object_id = models.PositiveIntegerField()
    reviewer = GenericForeignKey('reviewer_content_type', 'reviewer_object_id')

    class Meta:
        unique_together = ('assignment', 'reviewer_content_type', 'reviewer_object_id')


# ---------------------------------------------------------------------------
# 6. QuestionResponse — single source of truth for answers, with its own
#    draft/submit/approve/reject/resubmit lifecycle at the question level.
# ---------------------------------------------------------------------------

class QuestionResponse(WorkflowMixin, models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(BRSRQuestion, on_delete=models.CASCADE, related_name='responses')

    response_value = models.TextField(blank=True, null=True)
    response_json = models.JSONField(default=dict, blank=True)   # tables / structured answers
    answered_by_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    answered_by_object_id = models.PositiveIntegerField(null=True, blank=True)
    answered_by = GenericForeignKey('answered_by_content_type', 'answered_by_object_id')
    workflow_tasks = GenericRelation(
        'organizations.ApprovalConfigurationTask',
        content_type_field='target_content_type',
        object_id_field='target_object_id',
        related_query_name='brsr_question_response',
    )

    is_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('assignment', 'question')
        ordering = ['question__display_order']
        indexes = [models.Index(fields=['assignment', 'status'])]

    def save(self, *args, **kwargs):
        self.is_complete = bool(self.response_value or self.response_json)
        # snapshot a revision before overwriting, if this is an update
        if self.pk:
            previous = QuestionResponse.objects.filter(pk=self.pk).values(
                'response_value', 'response_json'
            ).first()
            if previous and (
                previous['response_value'] != self.response_value
                or previous['response_json'] != self.response_json
            ):
                ResponseRevision.objects.create(
                    response=self,
                    revision_number=self.revisions.count() + 1,
                    previous_value={
                        'response_value': previous['response_value'],
                        'response_json': previous['response_json'],
                    },
                    new_value={
                        'response_value': self.response_value,
                        'response_json': self.response_json,
                    },
                    changed_by_content_type=self.answered_by_content_type,
                    changed_by_object_id=self.answered_by_object_id,
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.assignment.plant.name} - {self.question.question_id}'

    @property
    def workflow_task(self):
        return self.workflow_tasks.select_related('template', 'current_stage').order_by('-created_at').first()

    @property
    def workflow_template(self):
        return self.assignment.workflow_template if self.assignment_id else None

    @property
    def workflow_stage(self):
        task = self.workflow_task
        return task.current_stage if task else None

    @property
    def workflow_stage_label(self):
        stage = self.workflow_stage
        return stage.label if stage else ''

    @property
    def workflow_stage_type(self):
        stage = self.workflow_stage
        return stage.stage_type if stage else ''

    def _ensure_workflow_task(self, first_assignee=None):
        template = self.workflow_template
        if not template:
            return None

        task = self.workflow_task
        if task:
            return task

        from apps.organizations.workflow_configuration_engine import WorkflowConfigurationEngine

        assignee = first_assignee or getattr(self.assignment, 'assignee', None) or self.answered_by
        if assignee is None:
            return None
        return WorkflowConfigurationEngine.start(template, self, assignee)

    def submit(self, user):
        task = self._ensure_workflow_task(
            first_assignee=getattr(self.assignment, "assignee", None)
        )

        self.status = (
            WorkflowStatus.RESUBMITTED
            if self.resubmission_count
            else WorkflowStatus.SUBMITTED
        )
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(update_fields=[
            "status",
            "submitted_by",
            "submitted_at",
        ])

        if task:
            WorkflowConfigurationEngine.advance_to_next_stage(
                task,
                user=user,
            )

    def approve(self, user, remark=''):
        task = self.workflow_task
        if task:
            from apps.organizations.workflow_configuration_engine import WorkflowConfigurationEngine

            WorkflowConfigurationEngine.approve(task, user, remark=remark)
            return
        super().approve(user, remark=remark)

    def reject(self, user, remark):
        task = self.workflow_task
        if task:
            from apps.organizations.workflow_configuration_engine import WorkflowConfigurationEngine

            WorkflowConfigurationEngine.reject(task, user, remark=remark)
            return
        super().reject(user, remark)

    def resubmit(self, user):
        self.resubmission_count += 1
        self.submit(user)


class ResponseRevision(models.Model):
    """Audit trail — who changed what, generic over actor type."""
    response = models.ForeignKey(QuestionResponse, on_delete=models.CASCADE, related_name='revisions')
    revision_number = models.PositiveIntegerField()

    changed_by_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    changed_by_object_id = models.PositiveIntegerField(null=True, blank=True)
    changed_by = GenericForeignKey('changed_by_content_type', 'changed_by_object_id')

    previous_value = models.JSONField()
    new_value = models.JSONField()
    change_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-revision_number']
        unique_together = ('response', 'revision_number')


def brsr_document_upload_path(instance, filename):
    assignment_id = instance.response.assignment.assignment_id
    return os.path.join("brsr", assignment_id, filename)


class QuestionResponseDocument(models.Model):
    response = models.ForeignKey(QuestionResponse, on_delete=models.CASCADE, related_name="documents",)
    document = models.FileField(upload_to=brsr_document_upload_path)
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True,)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name

class AssignmentSchedule(models.Model):

    FREQUENCY_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    ]

    WEEKDAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
        (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]

    MONTH_CHOICES = [
        (4, 'April'), (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
        (1, 'January'), (2, 'February'), (3, 'March'),
    ]

    QUARTER_CHOICES = [
        ('Q1', 'Q1 (Apr - Jun)'),
        ('Q2', 'Q2 (Jul - Sep)'),
        ('Q3', 'Q3 (Oct - Dec)'),
        ('Q4', 'Q4 (Jan - Mar)'),
    ]

    schedule_id = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=150, blank=True)

    plant = models.ForeignKey(
        'organizations.Plant', on_delete=models.CASCADE, related_name='assignment_schedules'
    )
    section = models.ForeignKey(
        'BRSRSection', on_delete=models.CASCADE, related_name='assignment_schedules'
    )
    principle = models.ForeignKey(
        'BRSRPrinciple', on_delete=models.CASCADE, null=True, blank=True,
        related_name='assignment_schedules',
    )
    questions = models.ManyToManyField('BRSRQuestion', related_name='assignment_schedules')

    workflow_template = models.ForeignKey(
        'organizations.ApprovalConfigurationTemplate',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='brsr_assignment_schedules',
    )
    financial_year = models.CharField(max_length=20)
    assignee_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    assignee_object_id = models.PositiveIntegerField()
    assignee = GenericForeignKey('assignee_content_type', 'assignee_object_id')
    reviewer_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    reviewer_object_id = models.PositiveIntegerField(null=True, blank=True)
    reviewer = GenericForeignKey('reviewer_content_type', 'reviewer_object_id')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    weekly_start_day = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES, null=True, blank=True)
    weekly_end_day = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES, null=True, blank=True)
    selected_months = models.JSONField(default=list, blank=True)
    selected_quarters = models.JSONField(default=list, blank=True)
    priority = models.CharField(max_length=10, choices=[
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent'),
    ], default='medium')
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'frequency']),
            models.Index(fields=['plant', 'financial_year']),
        ]

    def save(self, *args, **kwargs):
        if not self.schedule_id:
            plant_code = self.plant.name[:3].upper() if self.plant_id else 'SCH'
            year = timezone.now().year
            count = AssignmentSchedule.objects.filter(created_at__year=year).count() + 1
            self.schedule_id = f'SCH-{plant_code}-{year}-{count:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or self.schedule_id    