from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db.models import Count, Q
from .models import *

class QuestionInline(admin.TabularInline):
    """Inline for displaying questions within a principle or section."""
    model = BRSRQuestion
    extra = 0
    fields = (
        'question_id', 'question_number', 'question_text', 'question_type',
        'is_required', 'is_active', 'version', 'display_order'
    )
    readonly_fields = ('version', 'created_at', 'updated_at')
    ordering = ('display_order',)


class ResponseInline(admin.TabularInline):
    """Inline for responses within an assignment."""
    model = QuestionResponse
    extra = 0
    fields = (
        'question', 'status', 'is_complete', 'response_value_preview',
        'submitted_at', 'reviewed_by', 'reviewed_at'
    )
    readonly_fields = (
        'question', 'status', 'is_complete', 'response_value_preview',
        'submitted_at', 'reviewed_by', 'reviewed_at'
    )
    can_delete = False
    show_change_link = True

    def response_value_preview(self, obj):
        if obj.response_value:
            return obj.response_value[:100] + ('...' if len(obj.response_value) > 100 else '')
        if obj.response_json:
            return 'JSON data'
        return '-'
    response_value_preview.short_description = 'Response Preview'


class RevisionInline(admin.TabularInline):
    """Inline for displaying response revisions."""
    model = ResponseRevision
    extra = 0
    fields = (
        'revision_number', 'change_summary', 'changed_by', 'created_at'
    )
    readonly_fields = fields
    can_delete = False
    ordering = ('-revision_number',)


class ReviewerInline(GenericTabularInline):
    """Generic inline for assignment reviewers."""
    model = AssignmentReviewer
    extra = 1
    fields = ('reviewer',)
    ct_field = 'reviewer_content_type'
    ct_fk_field = 'reviewer_object_id'


# ============================================================================
# 2. Model Admin Classes
# ============================================================================

@admin.register(BRSRSection)
class BRSRSectionAdmin(admin.ModelAdmin):
    """Admin interface for BRSR Sections."""
    list_display = ('code', 'name', 'display_order', 'is_active', 'question_count')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    ordering = ('display_order', 'code')
    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'display_order', 'is_active')
        }),
    )
    
    def question_count(self, obj):
        return obj.questions.filter(is_active=True).count()
    question_count.short_description = 'Active Questions'
    question_count.admin_order_field = 'questions__count'


@admin.register(BRSRPrinciple)
class BRSRPrincipleAdmin(admin.ModelAdmin):
    """Admin interface for BRSR Principles."""
    list_display = (
        'principle_number', 'principle_name', 'title_preview', 'version',
        'is_active', 'question_count', 'assignment_count'
    )
    list_filter = ('is_active', 'version')
    search_fields = ('principle_name', 'title', 'slug')
    readonly_fields = ('slug',)
    prepopulated_fields = {'slug': ('principle_name',)}
    inlines = [QuestionInline]
    fieldsets = (
        (None, {
            'fields': (
                'principle_number', 'principle_name', 'title', 'img',
                'slug', 'version', 'is_active'
            )
        }),
    )

    def title_preview(self, obj):
        return obj.title[:50] + ('...' if len(obj.title) > 50 else '')
    title_preview.short_description = 'Title'

    def question_count(self, obj):
        return obj.questions.filter(is_active=True).count()
    question_count.short_description = 'Active Questions'

    def assignment_count(self, obj):
        return obj.assignments.count()
    assignment_count.short_description = 'Assignments'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            question_count=Count('questions', filter=Q(questions__is_active=True))
        )


@admin.register(BRSRQuestion)
class BRSRQuestionAdmin(admin.ModelAdmin):
    """Admin interface for BRSR Questions."""
    list_display = (
        'question_id', 'question_preview', 'section', 'principle',
        'question_type', 'version', 'is_active', 'is_required', 'display_order'
    )
    list_filter = (
        'section', 'principle', 'question_type', 'is_active', 'is_required'
    )
    search_fields = ('question_id', 'question_text', 'question_number')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('section', 'principle', 'display_order')
    fieldsets = (
        (None, {
            'fields': (
                'question_id', 'section', 'principle', 'question_text',
                'question_number', 'question_type', 'is_required',
                'display_order', 'is_active'
            )
        }),
        ('Advanced Options', {
            'fields': (
                'help_text', 'placeholder_text', 'options', 'validation_rules',
                'sub_section', 'parent_question'
            ),
            'classes': ('collapse',)
        }),
        ('Versioning', {
            'fields': (
                'version', 'supersedes', 'effective_from', 'effective_to'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def question_preview(self, obj):
        return obj.question_text[:50] + ('...' if len(obj.question_text) > 50 else '')
    question_preview.short_description = 'Question'


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    """Admin interface for Assignments."""
    list_display = (
        'assignment_id', 'plant', 'principle', 'section', 'workflow_template_display', 'workflow_stage_display',
        'assignee',
        'priority', 'due_date_display', 'overall_status_display',
        'question_count'
    )
    list_filter = (
        'plant', 'principle', 'section', 'priority', 'financial_year',
        'data_collection_frequency'
    )
    search_fields = (
        'assignment_id', 'plant__name', 'principle__principle_name'
    )
    readonly_fields = ('assignment_id', 'created_at', 'updated_at')
    raw_id_fields = ('plant', 'principle', 'section')
    inlines = [ReviewerInline, ResponseInline]
    fieldsets = (
        (None, {
            'fields': (
                'assignment_id', 'plant', 'principle', 'section', 'workflow_template',
                'financial_year', 'questions'
            )
        }),
        ('Assignment Details', {
            'fields': (
                'parent', 'assigner', 'assignee', 'due_date',
                'priority', 'notes'
            )
        }),
        ('Data Collection', {
            'fields': (
                'data_collection_frequency', 'selected_months',
                'selected_quarters'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def due_date_display(self, obj):
        if obj.due_date:
            if obj.is_overdue:
                return format_html(
                    '<span style="color:red;">{}</span>',
                    obj.due_date.strftime('%Y-%m-%d')
                )
            return obj.due_date.strftime('%Y-%m-%d')
        return '-'
    due_date_display.short_description = 'Due Date'

    def overall_status_display(self, obj):
        status = obj.overall_status
        colors = {
            'pending': 'gray',
            'in_progress': 'orange',
            'completed': 'green',
            'needs_revision': 'red',
            'rejected': 'red',
            'reassigned': 'orange',
        }
        color = colors.get(status, 'black')
        return format_html(
            '<span style="color:{};font-weight:bold;">{}</span>',
            color, status.replace('_', ' ').title()
        )
    overall_status_display.short_description = 'Status'

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'

    def workflow_template_display(self, obj):
        return obj.workflow_template.name if obj.workflow_template_id else '-'
    workflow_template_display.short_description = 'Workflow Template'

    def workflow_stage_display(self, obj):
        return obj.workflow_stage_label or '-'
    workflow_stage_display.short_description = 'Current Stage'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'questions', 'responses'
        )


@admin.register(QuestionResponse)
class QuestionResponseAdmin(admin.ModelAdmin):
    """Admin interface for Question Responses."""
    list_display = (
        'id', 'assignment_link', 'question_link', 'status_display',
        'is_complete', 'respondent', 'submitted_at', 'review_status'
    )
    list_filter = ('status', 'is_complete', 'submitted_at', 'reviewed_at')
    search_fields = (
        'assignment__assignment_id', 'question__question_text',
        'response_value'
    )
    readonly_fields = (
        'assignment', 'question', 'created_at', 'updated_at',
        'revision_count'
    )
    raw_id_fields = ('assignment', 'question')
    inlines = [RevisionInline]
    fieldsets = (
        (None, {
            'fields': (
                'assignment', 'question', 'status', 'is_complete'
            )
        }),
        ('Response Data', {
            'fields': ('response_value', 'response_json', 'uploaded_files')
        }),
        ('Workflow', {
            'fields': (
                'submitted_by', 'submitted_at', 'reviewed_by',
                'reviewed_at', 'review_remark', 'resubmission_count'
            ),
            'classes': ('collapse',)
        }),
        ('Actor', {
            'fields': ('answered_by',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'revision_count'),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        status_map = {
            'draft': '📝 Draft',
            'submitted': '📤 Submitted',
            'approved': '✅ Approved',
            'rejected': '❌ Rejected',
            'resubmitted': '🔄 Resubmitted'
        }
        return status_map.get(obj.status, obj.status)
    status_display.short_description = 'Status'

    def assignment_link(self, obj):
        url = reverse('admin:brsr_assignment_change', args=[obj.assignment.id])
        return format_html('<a href="{}">{}</a>', url, obj.assignment.assignment_id)
    assignment_link.short_description = 'Assignment'

    def question_link(self, obj):
        url = reverse('admin:brsr_question_change', args=[obj.question.id])
        return format_html('<a href="{}">{}</a>', url, obj.question.question_id)
    question_link.short_description = 'Question'

    def respondent(self, obj):
        return obj.answered_by or '-'
    respondent.short_description = 'Answered By'

    def review_status(self, obj):
        if obj.status in ['approved', 'rejected']:
            return format_html(
                '{} by {}',
                obj.status.title(),
                obj.reviewed_by or 'unknown'
            )
        return '-'
    review_status.short_description = 'Review'

    def revision_count(self, obj):
        return obj.revisions.count()
    revision_count.short_description = 'Revisions'


@admin.register(ResponseRevision)
class ResponseRevisionAdmin(admin.ModelAdmin):
    """Admin interface for Response Revisions."""
    list_display = (
        'id', 'response', 'revision_number', 'changed_by',
        'change_summary_preview', 'created_at'
    )
    list_filter = ('created_at',)
    search_fields = (
        'response__assignment__assignment_id',
        'response__question__question_text',
        'change_summary'
    )
    readonly_fields = (
        'response', 'revision_number', 'previous_value', 'new_value',
        'changed_by', 'change_summary', 'created_at'
    )
    fieldsets = (
        (None, {
            'fields': ('response', 'revision_number', 'changed_by')
        }),
        ('Changes', {
            'fields': ('previous_value', 'new_value', 'change_summary')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )

    def change_summary_preview(self, obj):
        if obj.change_summary:
            return obj.change_summary[:100] + ('...' if len(obj.change_summary) > 100 else '')
        return 'No summary'
    change_summary_preview.short_description = 'Summary'


@admin.action(description='Approve selected responses')
def approve_responses(modeladmin, request, queryset):
    """Custom action to approve multiple responses."""
    count = 0
    for response in queryset.filter(status__in=['submitted', 'resubmitted']):
        response.approve(request.user, 'Approved via admin bulk action')
        count += 1
    modeladmin.message_user(request, f'{count} responses approved.')


@admin.action(description='Reject selected responses')
def reject_responses(modeladmin, request, queryset):
    """Custom action to reject multiple responses."""
    count = 0
    for response in queryset.filter(status__in=['submitted', 'resubmitted']):
        response.reject(request.user, 'Rejected via admin bulk action')
        count += 1
    modeladmin.message_user(request, f'{count} responses rejected.')

QuestionResponseAdmin.actions = [approve_responses, reject_responses]


class OverdueFilter(admin.SimpleListFilter):
    """Custom filter for overdue assignments."""
    title = _('Overdue Status')
    parameter_name = 'overdue'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Overdue')),
            ('no', _('Not Overdue')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(
                due_date__lt=timezone.now().date()
            ).exclude(overall_status='completed')
        if self.value() == 'no':
            return queryset.filter(
                Q(due_date__gte=timezone.now().date()) | Q(due_date__isnull=True)
            )
        return queryset

AssignmentAdmin.list_filter = list(AssignmentAdmin.list_filter) + [OverdueFilter]

@admin.action(description="Activate selected schedules")
def activate_schedules(modeladmin, request, queryset):
    queryset.update(is_active=True)
 
 
@admin.action(description="Deactivate selected schedules")
def deactivate_schedules(modeladmin, request, queryset):
    queryset.update(is_active=False)
 
 
@admin.register(AssignmentSchedule)
class AssignmentScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "schedule_id", "name", "plant", "section", "principle",
        "frequency", "financial_year", "is_active", "created_at",
    )
    list_filter = ("frequency", "is_active", "plant", "section")
    search_fields = ("schedule_id", "name", "plant__name")
    readonly_fields = ("schedule_id", "created_at", "updated_at")
    filter_horizontal = ("questions",)
    actions = [activate_schedules, deactivate_schedules]
 