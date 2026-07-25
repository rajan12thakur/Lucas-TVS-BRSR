import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import TemplateView
from apps.accounts.models import Department
from apps.organizations.models import ApprovalConfigurationTemplate, FinancialYear, Plant
from apps.organizations.workflow_configuration_engine import WorkflowConfigurationEngine
from .forms import BRSRAssignmentForm, AssignmentScheduleForm
from .models import Assignment, AssignmentReviewer, BRSRPrinciple, BRSRQuestion, BRSRSection, QuestionResponse, QuestionResponseDocument, AssignmentSchedule
from django.db.models import Case, When, Value, IntegerField


User = get_user_model()

def _section_scope_queryset():
    return (
        BRSRSection.objects.filter(is_active=True)
        .order_by("display_order", "code")
        .prefetch_related("questions")
    )

def _principle_queryset():
    return (
        BRSRPrinciple.objects.filter(is_active=True)
        .order_by("principle_number")
        .prefetch_related("questions")
    )

def _pdf_questions_queryset():
    return BRSRQuestion.objects.filter(is_active=True)

def _get_default_section():
    return BRSRSection.objects.filter(is_active=True).order_by("display_order", "code").first()

def _get_default_principle():
    return BRSRPrinciple.objects.filter(is_active=True).order_by("principle_number").first()


def _workflow_template_queryset():
    return (
        ApprovalConfigurationTemplate.objects.filter(is_active=True, framework="BRSR")
        .select_related("company")
        .prefetch_related("stages", "stages__role", "stages__escalation_role")
        .order_by("company__company_name", "name")
    )


def _workflow_stage_by_type(template, stage_type):
    if not template or not stage_type:
        return None
    return template.stages.filter(stage_type=stage_type).order_by("level").first()


def _workflow_entry_stage(template):
    if not template:
        return None

    first_stage = template.first_stage
    if not first_stage:
        return None

    if first_stage.stage_type == "question_assignment":
        next_stage = first_stage.next_stage()
        if next_stage:
            return next_stage

    return first_stage


def _company_scope_plants(user):
    queryset = Plant.objects.filter(is_active=True)
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return queryset.order_by("name")
    if getattr(user, "company_id", None):
        return queryset.filter(created_by__company_id=user.company_id).order_by("name")
    return queryset.filter(id__in=user.assigned_plants.filter(is_active=True).values_list("id", flat=True)).order_by("name")


def _assignment_queryset_for_user(user):
    queryset = Assignment.objects.all()
    if user.is_superuser or getattr(user, "is_super_admin", False):
        return queryset
    if getattr(user, "company_id", None):
        return queryset.filter(plant__created_by__company_id=user.company_id)
    plant_ids = user.assigned_plants.filter(is_active=True).values_list("id", flat=True)
    return queryset.filter(plant_id__in=plant_ids)


def _resolve_brsr_workflow_template(user=None, plant=None):
    queryset = _workflow_template_queryset()

    company_id = getattr(user, "company_id", None)
    if company_id:
        template = queryset.filter(company_id=company_id).first()
        if template:
            return template

    plant_company_id = getattr(getattr(plant, "created_by", None), "company_id", None)
    if plant_company_id:
        template = queryset.filter(company_id=plant_company_id).first()
        if template:
            return template

    return queryset.first()


def _workflow_assignees_for_stage(plant, stage, current_user=None):
    if not plant:
        return User.objects.none()

    if not stage or not stage.role_id:
        return _plant_assignees(plant, current_user=current_user)

    queryset = (
        User.objects.filter(
            is_active=True,
            assigned_plants=plant,
            role_id=stage.role_id,
        )
        .select_related("role", "department")
        .order_by("full_name", "username")
    )
    plant_company_id = getattr(getattr(plant, "created_by", None), "company_id", None)
    if plant_company_id:
        queryset = queryset.filter(company_id=plant_company_id)
    if current_user:
        queryset = queryset.exclude(pk=current_user.pk)
    queryset = queryset.distinct()
    if queryset.exists() or not stage or not stage.role_id:
        return queryset

    fallback = (
        User.objects.filter(
            is_active=True,
            role_id=stage.role_id,
        )
        .select_related("role", "department")
        .order_by("full_name", "username")
    )
    if plant_company_id:
        fallback = fallback.filter(company_id=plant_company_id)
    if current_user:
        fallback = fallback.exclude(pk=current_user.pk)
    fallback = fallback.distinct()
    if fallback.exists() or not stage or stage.stage_type != "review":
        return fallback

    company_users = (
        User.objects.filter(
            is_active=True,
            company_id=plant_company_id,
        )
        .select_related("role", "department")
        .order_by("full_name", "username")
    )
    if current_user:
        company_users = company_users.exclude(pk=current_user.pk)
    return company_users.distinct()


def _reviewer_links_for_assignment(assignment):
    if not assignment:
        return []
    return [link.reviewer for link in assignment.reviewer_links.select_related("reviewer_content_type").all() if link.reviewer]


def _assigned_reviewer_ids_for_assignment(assignment):
    if not assignment:
        return []
    return [link.reviewer_object_id for link in assignment.reviewer_links.all() if link.reviewer_object_id]


def _is_assigned_reviewer(user, assignment):
    if not user or not getattr(user, "is_authenticated", False) or not assignment:
        return False
    return user.id in _assigned_reviewer_ids_for_assignment(assignment)


def _first_workflow_assignee_for_stage(plant, stage, current_user=None, assignment=None):
    if assignment and stage and stage.stage_type == "review":
        assigned_reviewers = _reviewer_links_for_assignment(assignment)
        eligible_reviewers = _workflow_assignees_for_stage(plant, stage, current_user=current_user)
        for reviewer in assigned_reviewers:
            if reviewer and eligible_reviewers.filter(pk=reviewer.pk).exists():
                return reviewer

    assignee = _workflow_assignees_for_stage(plant, stage, current_user=current_user).first()
    if stage and stage.role_id and assignee is None:
        raise ValueError(f"No eligible assignee found for stage '{stage.label}'.")
    return assignee


def _resolve_brsr_assignee(plant, template, selected_assignee=None, current_user=None):
    stage = _workflow_entry_stage(template) if template else None
    if not stage or not stage.role_id:
        return selected_assignee or _workflow_assignees_for_stage(plant, stage, current_user=current_user).first()

    eligible = _workflow_assignees_for_stage(plant, stage, current_user=current_user)
    if selected_assignee and eligible.filter(pk=selected_assignee.pk).exists():
        return selected_assignee

    default_assignee = eligible.first()
    if default_assignee:
        return default_assignee

    raise ValueError("No eligible assignee matches the first stage of the configured BRSR workflow.")


def _resolve_brsr_reviewer(plant, template, selected_reviewer=None, current_user=None):
    review_stage = _workflow_stage_by_type(template, "review")
    if not review_stage or not review_stage.role_id:
        return selected_reviewer

    eligible = _workflow_assignees_for_stage(plant, review_stage, current_user=current_user)
    if selected_reviewer and eligible.filter(pk=selected_reviewer.pk).exists():
        return selected_reviewer

    return None


def _next_non_review_stage(stage):
    next_stage = stage.next_stage() if stage else None
    while next_stage and next_stage.stage_type == "review":
        next_stage = next_stage.next_stage()
    return next_stage


def _advance_assignment_to_entry_stage(assignment, actor=None):
    """
    If the workflow starts with a question-assignment gate, move it forward to
    the actual data-entry stage so the assignee can work on the response.
    """
    task = assignment.workflow_task
    if not task or not task.current_stage_id:
        return task

    current_stage = task.current_stage
    if not current_stage or current_stage.stage_type != "question_assignment":
        return task

    next_stage = current_stage.next_stage()
    if not next_stage:
        return task

    if next_stage.stage_type != "data_entry":
        return task

    assignee_role_id = getattr(getattr(assignment, "assignee", None), "role_id", None)
    if next_stage.role_id and assignee_role_id != next_stage.role_id:
        return task

    WorkflowConfigurationEngine.advance_to_next_stage(
        task,
        assignment.assigner or actor or assignment.assignee,
        remark="Auto-advanced to data entry stage after assignment creation.",
        next_assignee=assignment.assignee,
    )
    return task


def _is_approval_stage(stage_type):
    return stage_type in {"review", "approval", "pre_final_approval", "final_approval"}


def _approval_stage_queryset(user):
    assignments = _assignment_queryset_for_user(user).select_related(
        "plant",
        "section",
        "principle",
        "workflow_template",
        "assignee_content_type",
        "assigner_content_type",
    ).prefetch_related(
        "questions",
        "responses",
        "questions__section",
        "questions__principle",
    )
    actionable = []
    for assignment in assignments:
        _ensure_assignment_workflow_task(assignment, current_user=user)
        if assignment.workflow_stage_type and _is_approval_stage(assignment.workflow_stage_type):
            actionable.append(assignment)
    return actionable


def _serialize_workflow_task(task):
    if not task:
        return None
    is_completed = bool(task.is_completed)
    stage_label = "Final Approved & Locked" if is_completed else (task.current_stage.label if task.current_stage_id else "")
    stage_type = "" if is_completed else (task.current_stage.stage_type if task.current_stage_id else "")
    return {
        "id": task.id,
        "template": task.template.name if task.template_id else "",
        "stage": stage_label,
        "stage_type": stage_type,
        "stage_level": task.current_stage.level if task.current_stage_id else None,
        "assignee": "" if is_completed else (str(task.current_assignee) if task.current_assignee else ""),
        "is_completed": task.is_completed,
        "is_returned": task.is_returned,
        "is_overdue": task.is_overdue,
        "history_url": reverse("organizations:workflow_configuration_task_history", kwargs={"pk": task.pk}),
    }


def _ensure_assignment_workflow_task(assignment, current_user=None):
    if assignment.workflow_task:
        task = assignment.workflow_task
        _advance_assignment_to_entry_stage(assignment, actor=current_user)
        return task
    template = assignment.workflow_template
    if not template:
        template = _resolve_brsr_workflow_template(user=current_user, plant=assignment.plant)
        if template:
            assignment.workflow_template = template
            assignment.save(update_fields=["workflow_template", "updated_at"])
    if not template or not template.first_stage:
        return None
    first_assignee = assignment.assignee or current_user
    if first_assignee is None:
        return None
    task = WorkflowConfigurationEngine.start(template, assignment, first_assignee)
    _advance_assignment_to_entry_stage(assignment, actor=current_user)
    return task

def _get_section_principle(section_code=None, principle_slug=None):
    section = None
    principle = None

    if section_code:
        section = get_object_or_404(BRSRSection, code=section_code, is_active=True)
    else:
        section = _get_default_section()

    if section and section.code == "section_c":
        principles = _principle_queryset()
        if principle_slug:
            principle = get_object_or_404(BRSRPrinciple, slug=principle_slug, is_active=True)
        else:
            principle = principles.first()
    return section, principle


def _question_queryset(section, principle=None):
    qs = (
        _pdf_questions_queryset().filter(section=section)
        .select_related("section", "principle", "parent_question")
        .order_by("display_order", "question_number")
    )
    if section.code == "section_c":
        if principle:
            qs = qs.filter(principle=principle)
        else:
            qs = qs.filter(principle__isnull=False)
    else:
        qs = qs.filter(principle__isnull=True)
    return qs


def _question_status(question, assignment=None):
    response_qs = QuestionResponse.objects.filter(question=question)
    if assignment is not None:
        response_qs = response_qs.filter(assignment=assignment)
    response = response_qs.select_related("assignment").order_by("-updated_at", "-created_at").first()
    if response:
        return response.status
    return "draft"

def _question_metadata(question):
    rules = question.validation_rules or {}
    return {
        "parent_question_id": question.parent_question.question_id if question.parent_question else "",
        "table_schema": rules.get("table_schema", {}) or {},
        "conditional_logic": rules.get("conditional_logic", {}) or {},
        "allowed_values": rules.get("allowed_values", []) or [],
        "units": rules.get("units", "") or "",
        "default_value": rules.get("default_value"),
        "component_type": rules.get("component_type", question.question_type),
        "source_excerpt": rules.get("source_excerpt", "") or "",
    }


def _workflow_counts(questions, assignment=None):
    question_ids = [q.id for q in questions]
    responses = QuestionResponse.objects.filter(question_id__in=question_ids)
    if assignment is not None:
        responses = responses.filter(assignment=assignment)
    total = len(question_ids)
    completed = responses.filter(status="approved").values("question_id").distinct().count()
    submitted = responses.filter(status__in=["submitted", "resubmitted"]).values("question_id").distinct().count()
    rejected = responses.filter(status="rejected").values("question_id").distinct().count()
    return {
        "total": total,
        "completed": completed,
        "submitted": submitted,
        "rejected": rejected,
        "progress": round((completed / total * 100), 1) if total else 0,
    }


def _assignment_missing_responses(assignment):
    if not assignment:
        return []

    questions = list(
        assignment.questions.select_related("section", "principle").order_by("display_order", "question_number")
    )
    responses = {response.question_id: response for response in assignment.responses.all()}
    missing = []
    for question in questions:
        response = responses.get(question.id)
        response_value = (response.response_value or "").strip() if response else ""
        response_json = response.response_json if response else {}
        if response and (response_value or response_json):
            continue
        missing.append(
            {
                "question_id": question.question_id,
                "question_number": question.question_number,
                "title": question.question_text,
                "section": question.section.name if question.section_id else "",
                "sub_section": question.sub_section or "",
            }
        )
    return missing


def _actor_content_type_map():
    return {
        "user": ContentType.objects.get_for_model(User),
        "department": ContentType.objects.get_for_model(Department),
        "plant": ContentType.objects.get_for_model(Plant),
    }


def _actor_label(actor):
    if not actor:
        return ""
    if hasattr(actor, "full_name") and actor.full_name:
        return actor.full_name
    if hasattr(actor, "name") and actor.name:
        return actor.name
    return str(actor)


def _get_assignment_scope(user):
    role_code = getattr(getattr(user, "role", None), "role_code", "") or ""
    if user.is_superuser or user.is_super_admin or role_code == "COMPANYADMIN":
        return "plant"
    if role_code in {"PLANT-COORD", "PLANT_COORD", "PLANTCOORD"}:
        return "department"
    if role_code in {"DEPT-APPR", "DEPT-USER", "DEPARTMENT-USER", "DEPARTMENT-APPR"}:
        return "user"
    if getattr(user, "department_id", None) and user.assigned_plants.exists():
        return "department"
    return "user"


def _assignment_scope_queryset(user, plant=None, department=None):
    role_code = getattr(getattr(user, "role", None), "role_code", "") or ""
    if user.is_superuser or user.is_super_admin or role_code == "COMPANYADMIN":
        return Assignment.objects.all()

    ct_map = _actor_content_type_map()
    filters = Q(assignee_content_type=ct_map["user"], assignee_object_id=user.id)
    reviewer_content_type = ContentType.objects.get_for_model(User)
    reviewer_assignments = Assignment.objects.filter(
        reviewer_links__reviewer_content_type=reviewer_content_type,
        reviewer_links__reviewer_object_id=user.id
    )
    filters |= Q(id__in=reviewer_assignments.values_list('id', flat=True))

    plant_ids = list(user.assigned_plants.filter(is_active=True).values_list("id", flat=True))
    if plant_ids:
        filters |= Q(assignee_content_type=ct_map["plant"], assignee_object_id__in=plant_ids)

    if getattr(user, "department_id", None):
        filters |= Q(
            assignee_content_type=ct_map["department"],
            assignee_object_id=user.department_id,
        )

    if plant:
        filters |= Q(plant=plant)
    if department:
        filters |= Q(assignee_content_type=ct_map["department"], assignee_object_id=department.id)
    return Assignment.objects.filter(filters).distinct()

def _plant_departments(plant):
    if not plant:
        return Department.objects.none()
    return (
        Department.objects.filter(users__assigned_plants=plant, is_active=True)
        .distinct()
        .order_by("name")
    )


def _assignment_target_role_codes(user):
    role_code = getattr(getattr(user, "role", None), "role_code", "") or ""
    if user.is_superuser or user.is_super_admin or role_code == "COMPANYADMIN":
        return ["PLANT-COORD", "PLANT_COORD", "PLANTCOORD"]
    if role_code in {"PLANT-COORD", "PLANT_COORD", "PLANTCOORD"}:
        return ["DEPT-APPR", "DEPT-USER", "DEPARTMENT-USER", "DEPARTMENT-APPR"]
    return ["DEPT-USER", "DEPT-APPR", "DEPARTMENT-USER", "DEPARTMENT-APPR"]


def _plant_assignees(plant, target_role_codes=None, current_user=None):
    if not plant:
        return User.objects.none()

    queryset = (
        User.objects.filter(is_active=True, assigned_plants=plant,)
        .exclude(Q(is_superuser=True) | Q(role__role_code__in=["SUPERADMIN", "COMPANYADMIN"]))
        .select_related("department", "role")
        .order_by("full_name", "username")
    )

    if target_role_codes:
        queryset = queryset.filter(role__role_code__in=target_role_codes)
    if current_user:
        queryset = queryset.exclude(pk=current_user.pk)

    return queryset.distinct()

def _default_assignee_for_context(user, plant):
    assignees = _plant_assignees(plant, target_role_codes=_assignment_target_role_codes(user), current_user=user)
    if not assignees.exists():
        return None

    role_rank = {
        "COMPANYADMIN": 0,
        "SUPERADMIN": 0,
        "PLANT-COORD": 1,
        "PLANT_COORD": 1,
        "DEPT-APPR": 2,
        "DEPT-USER": 3,
        "COMPANYUSER": 4,
    }

    def sort_key(item):
        role_code = getattr(getattr(item, "role", None), "role_code", "") or ""
        return (
            role_rank.get(role_code, 99),
            item.department_id or 999999,
            item.full_name or item.username,
        )

    return sorted(assignees, key=sort_key)[0]


def _serialize_assignment(assignment, user=None):
    questions = list(assignment.questions.select_related("section", "principle").order_by("display_order", "question_number"))
    first_question = questions[0] if questions else None
    workflow_task = assignment.workflow_task
    workflow_completed = bool(workflow_task and workflow_task.is_completed)
    assignment_status = getattr(assignment, "assignment_status", "") or ""
    assignment_status_label = {
        "pending": "Pending",
        "in_progress": "In Progress",
        "rejected": "Rejected",
        "reassigned": "Reassigned",
        "approved": "Approved",
    }.get(assignment_status, assignment_status.replace("_", " ").title() if assignment_status else "")
    response_map = {
        response.question_id: response.status
        for response in assignment.responses.all().only("question_id", "status")
    }
    workflow_status_label = "Final Approved & Locked" if workflow_completed else (assignment_status_label or assignment.workflow_stage_label)
    current_user_role = None

    if user and assignment.workflow_task and assignment.workflow_task.current_stage:
        stage_type = assignment.workflow_task.current_stage.stage_type

        if stage_type == "review" and _is_assigned_reviewer(user, assignment):
            current_user_role = "review"

        elif stage_type in ["approval", "pre_final_approval", "final_approval"]:
            task_info = _serialize_task_for_user(assignment.workflow_task, user)
            if task_info and task_info.get("can_act"):
                current_user_role = "approval"
    return {
        "id": assignment.id,
        "assignment_id": assignment.assignment_id,
        "plant": assignment.plant.name if assignment.plant_id else "",
        "plant_code": assignment.plant.code if assignment.plant_id else "",
        "assignee": "" if workflow_completed else _actor_label(assignment.assignee),
        "assignee_type": assignment.assignee_content_type.model if assignment.assignee_content_type_id else "",
        "assigner": _actor_label(assignment.assigner),
        "section": assignment.section.name if assignment.section_id else "",
        "section_code": assignment.section.code if assignment.section_id else "",
        "principle": assignment.principle.principle_name if assignment.principle_id else "",
        "financial_year": assignment.financial_year,
        "workflow_template": assignment.workflow_template_name,
        "workflow_stage": "" if workflow_completed else assignment.workflow_stage_label,
        "workflow_stage_type": "" if workflow_completed else assignment.workflow_stage_type,
        "workflow_status_label": workflow_status_label,
        "assignment_status": assignment_status,
        "assignment_status_label": assignment_status_label,
        "is_editable": assignment.is_editable,
        "is_assigned_reviewer": _is_assigned_reviewer(user, assignment) if user else False,
        "workflow_task": _serialize_workflow_task(workflow_task),
        "due_date": assignment.due_date.isoformat() if assignment.due_date else "",
        "priority": assignment.priority,
        "overall_status": assignment.overall_status,
        "is_overdue": assignment.is_overdue,
        "question_count": len(questions),
        "questions": [
            {
                "id": question.id,
                "question_id": question.question_id,
                "title": question.question_text,
                "number": question.question_number,
                "section_code": question.section.code,
                "principle_slug": question.principle.slug if question.principle else "",
                "status": response_map.get(question.id, "draft"),
            }
            for question in questions
        ],
        "workspace_url": (
            (
                reverse(
                    "brsr:question_workspace_principle",
                    kwargs={
                        "section_code": first_question.section.code,
                        "principle_slug": first_question.principle.slug,
                    },
                )
                if first_question and first_question.principle
                else reverse(
                    "brsr:question_workspace_section",
                    kwargs={"section_code": first_question.section.code},
                )
                if first_question
                else ""
            )
            + (f"?assignment_id={assignment.id}" if assignment.id else "")
        ),
        "current_user_role": current_user_role,
    }

def _serialize_assignment_with_reviewers(assignment, user=None):
    """Serialize assignment with reviewer information and comments."""
    base_data = _serialize_assignment(assignment, user)
    
    # Add reviewer information
    reviewer_links = assignment.reviewer_links.select_related('reviewer_content_type').all()
    reviewers = []
    for link in reviewer_links:
        reviewer = link.reviewer
        if reviewer:
            reviewers.append({
                "id": reviewer.id,
                "name": _actor_label(reviewer),
                "type": link.reviewer_content_type.model if link.reviewer_content_type_id else "user",
            })
    
    responses_with_comments = []
    for response in assignment.responses.select_related('question').all():
        if response.review_remark:  
            responses_with_comments.append({
                "question_id": response.question.question_id,
                "question_number": response.question.question_number,
                "question_text": response.question.question_text,
                "review_remark": response.review_remark,
                "reviewed_by": _actor_label(response.reviewed_by) if response.reviewed_by else "",
                "reviewed_at": response.reviewed_at.isoformat() if response.reviewed_at else "",
                "status": response.status,
            })
    
    base_data.update({
        "reviewers": reviewers,
        "review_comments": responses_with_comments,
        "has_review_comments": len(responses_with_comments) > 0,
        "is_assigned_reviewer": _is_assigned_reviewer(user, assignment) if user else False,
        "review_comments_count": len(responses_with_comments),
    })
    
    return base_data

def _assignment_context(section, principle, questions, assignment=None, user=None):
    latest_assignment = (
        Assignment.objects.filter(section=section, principle=principle)
        .select_related("plant")
        .order_by("-created_at")
        .first()
    )
    plant_qs = _company_scope_plants(user) if user else Plant.objects.filter(is_active=True).order_by("name")
    user_qs = User.objects.filter(is_active=True).select_related("role", "department").order_by(
        "full_name", "username"
    )
    fy_qs = FinancialYear.objects.all().order_by("-start_date")
    # Parent assignment / delegation removed from workflow
    return {
        "latest_assignment": latest_assignment,
        "current_assignment": assignment,
        "assignment_form": BRSRAssignmentForm(
            plant_queryset=plant_qs,
            user_queryset=user_qs,
            question_queryset=questions,
            financial_year_queryset=fy_qs,
        ),
        "plants": plant_qs,
        "users": user_qs,
        "financial_years": fy_qs,
        "assignment_schedule_form": AssignmentScheduleForm(
            plant_queryset=plant_qs,
            user_queryset=user_qs,
            question_queryset=questions,
            financial_year_queryset=fy_qs,
        ),
    }


def _create_brsr_assignment(*, user, section, principle, cleaned_data, question_queryset, workflow_template_override=None):
    plant = cleaned_data["plant"]
    workflow_template = workflow_template_override or _resolve_brsr_workflow_template(user=user, plant=plant)
    if not workflow_template:
        raise ValueError("No active BRSR workflow template is configured for this company.")
    if not workflow_template.first_stage:
        raise ValueError("The configured BRSR workflow template has no stages.")

    assignee = _resolve_brsr_assignee(
        plant,
        workflow_template,
        selected_assignee=cleaned_data["assignee"],
        current_user=user,
    )
    if assignee is None:
        raise ValueError(
            "No eligible assignee matches the first stage of the configured BRSR workflow."
        )

    reviewer = _resolve_brsr_reviewer(
        plant,
        workflow_template,
        selected_reviewer=cleaned_data.get("reviewer"),
        current_user=user,
    )

    user_ct = ContentType.objects.get_for_model(User)
    assigner = cleaned_data.get("assigner") or user
    assignment = Assignment.objects.create(
        plant=plant,
        principle=principle,
        section=section,
        financial_year=cleaned_data["financial_year"],
        workflow_template=workflow_template,
        data_collection_frequency=cleaned_data.get("data_collection_frequency") or "",
        assigner_content_type=user_ct,
        assigner_object_id=assigner.pk,
        assignee_content_type=user_ct,
        assignee_object_id=assignee.pk,
        due_date=cleaned_data.get("due_date"),
        priority=cleaned_data["priority"],
        notes=cleaned_data.get("notes"),
    )
    assignment.questions.set(question_queryset)
    if reviewer is not None:
        AssignmentReviewer.objects.create(
            assignment=assignment,
            reviewer_content_type=user_ct,
            reviewer_object_id=reviewer.pk,
        )
    for question in question_queryset:
        QuestionResponse.objects.get_or_create(
            assignment=assignment,
            question=question,
        )
    _ensure_assignment_workflow_task(assignment, current_user=user)
    _advance_assignment_to_entry_stage(assignment, actor=user)
    return assignment

def _serialize_task_for_user(task, user):
    """Serialize workflow task with user permissions."""
    if not task:
        return None
    is_completed = bool(task.is_completed)
    stage_label = "Final Approved & Locked" if is_completed else (task.current_stage.label if task.current_stage_id else "")
    stage_type = "" if is_completed else (task.current_stage.stage_type if task.current_stage_id else "")
    
    assignee_id = task.current_assignee_object_id if (
        task.current_assignee_content_type_id and 
        task.current_assignee_content_type.model == "user"
    ) else None
    if is_completed:
        assignee_id = None
    
    current_user_role_id = getattr(user, "role_id", None)
    current_stage_role_id = task.current_stage.role_id if task.current_stage_id else None
    
    can_act = bool(
        user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, "is_super_admin", False)
            or assignee_id == user.id
            or (current_user_role_id and current_stage_role_id and current_user_role_id == current_stage_role_id)
        )
    )
    if task.is_returned and assignee_id == getattr(user, "id", None):
        can_act = True
    if task.current_stage_id and task.current_stage.stage_type == "review":
        assignment = getattr(task.target, "assignment", None) or (task.target if isinstance(task.target, Assignment) else None)
        can_act = _is_assigned_reviewer(user, assignment)
    if is_completed:
        can_act = False
    
    return {
        "id": task.id,
        "stage": stage_label,
        "stage_type": stage_type,
        "stage_role_code": task.current_stage.role.role_code if (
            task.current_stage_id and task.current_stage.role_id
        ) else "",
        "current_assignee_id": assignee_id,
        "current_assignee": "" if is_completed else (str(task.current_assignee) if task.current_assignee else ""),
        "can_act": can_act,
        "is_completed": is_completed,
        "status_label": "Final Approved & Locked" if is_completed else stage_label,
    }

def _format_response_data(response_json):
    """Format response JSON as HTML for display."""
    if not response_json:
        return ""
    
    html_parts = []
    
    # Check if it's the trainingAwareness structure
    if isinstance(response_json, dict) and 'trainingAwareness' in response_json:
        data = response_json['trainingAwareness']
        if isinstance(data, list) and data and isinstance(data[0], dict):
            headers = list(data[0].keys())
            html_parts.append('<div class="data-table-container">')
            html_parts.append('<table class="data-table">')
            html_parts.append('<thead><tr><th>#</th>')
            for header in headers:
                html_parts.append(f'<th>{header}</th>')
            html_parts.append('</tr></thead>')
            html_parts.append('<tbody>')
            for idx, row in enumerate(data, 1):
                html_parts.append('<tr>')
                html_parts.append(f'<td>{idx}</td>')
                for header in headers:
                    value = row.get(header, "—")
                    html_parts.append(f'<td>{value}</td>')
                html_parts.append('</tr>')
            html_parts.append('</tbody>')
            html_parts.append('</table>')
            html_parts.append('</div>')
            return "".join(html_parts)
    
    # Handle other JSON structures as key-value pairs
    if isinstance(response_json, dict):
        html_parts.append('<div class="kv-container">')
        for key, value in response_json.items():
            if isinstance(value, list):
                html_parts.append(f'<div class="sub-section-title">{key}</div>')
                for idx, item in enumerate(value, 1):
                    if isinstance(item, dict):
                        html_parts.append(f'<div class="kv-row"><span class="kv-key">Entry {idx}</span>')
                        html_parts.append('<span class="kv-value">')
                        for sub_key, sub_value in item.items():
                            html_parts.append(f'{sub_key}: {sub_value}<br>')
                        html_parts.append('</span></div>')
                    else:
                        html_parts.append(f'<div class="kv-row"><span class="kv-key">{idx}</span><span class="kv-value">{item}</span></div>')
            else:
                html_parts.append(f'<div class="kv-row"><span class="kv-key">{key}</span><span class="kv-value">{value}</span></div>')
        html_parts.append('</div>')
        return "".join(html_parts)
    
    # Fallback: return as string
    return f'<div class="response-body response-value">{json.dumps(response_json, indent=2)}</div>'

class BRSRDashboardView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "brsr/brsr_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = _section_scope_queryset()
        principles = _principle_queryset()

        section_cards = []
        for section in sections:
            question_count = _question_queryset(section).count()
            section_cards.append(
                {
                    "section": section,
                    "question_count": question_count,
                    "url": reverse("brsr:question_workspace_section", kwargs={"section_code": section.code}),
                }
            )

        principle_cards = []
        for principle in principles:
            principle_cards.append(
                {
                    "principle": principle,
                    "question_count": principle.questions.filter(is_active=True).count(),
                    "url": reverse(
                        "brsr:question_workspace_principle",
                        kwargs={"section_code": "section_c", "principle_slug": principle.slug},
                    ),
                }
            )

        context["section_cards"] = section_cards
        context["principle_cards"] = principle_cards
        context["workspace_url"] = reverse("brsr:question_workspace")
        context["total_questions"] = _pdf_questions_queryset().count()
        context["total_sections"] = sections.count()
        context["total_principles"] = principles.count()
        return context


class AssignmentDashboardView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "brsr/assignment_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assignments = list(
            _assignment_scope_queryset(user)
            .select_related(
                "plant",
                "section",
                "principle",
                "workflow_template",
                "assignee_content_type",
                "assigner_content_type",
            )
            .prefetch_related(
                "questions",
                "responses",
                "questions__section",
                "questions__principle",
                "responses__question",
                "reviewer_links",
                "reviewer_links__reviewer_content_type",
            )
        )
        assignments.sort(key=lambda x: (x.overall_status == "completed", -x.created_at.timestamp()))

        serialized_assignments = [
            _serialize_assignment_with_reviewers(assignment, user)  # Use updated serializer
            for assignment in assignments
        ]
        context["assignments"] = serialized_assignments
        context["assignment_count"] = len(serialized_assignments)
        context["open_count"] = sum(1 for item in serialized_assignments if item["overall_status"] != "completed")
        context["completed_count"] = sum(1 for item in serialized_assignments if item["overall_status"] == "completed")
        context["overdue_count"] = sum(1 for item in serialized_assignments if item["is_overdue"])
        context["assignment_scope"] = _get_assignment_scope(user)
        return context


class ApprovalDashboardView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "brsr/approval_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        assignments = [
            assignment
            for assignment in _approval_stage_queryset(user)
            if not assignment.workflow_task or not assignment.workflow_task.is_completed
        ]
        grouped = {}
        total_questions = 0
        stage_counts = {
            "review": 0,
            "approval": 0,
            "pre_final_approval": 0,
            "final_approval": 0,
        }
        for assignment in assignments:
            stage_type = assignment.workflow_stage_type or ""
            if stage_type in stage_counts:
                stage_counts[stage_type] += 1
            company = getattr(getattr(assignment.plant, "created_by", None), "company", None)
            company_key = company.company_name if company else "Unknown Company"
            plant_key = assignment.plant.name if assignment.plant_id else "Unknown Plant"
            company_bucket = grouped.setdefault(company_key, {})
            plant_bucket = company_bucket.setdefault(plant_key, [])
            questions = list(
                assignment.questions.select_related("section", "principle").order_by("display_order", "question_number")
            )
            responses = {
                response.question_id: response
                for response in assignment.responses.select_related("question")
            }
            question_rows = []
            for question in questions:
                response = responses.get(question.id)
                question_rows.append(
                    {
                        "question_id": question.question_id,
                        "title": question.question_text,
                        "number": question.question_number,
                        "status": response.status if response else "draft",
                        "status_display": "Final Approved & Locked" if (assignment.workflow_task and assignment.workflow_task.is_completed) else ((response.status if response else "draft").replace("_", " ").title()),
                        "workflow_stage": "Final Approved & Locked" if (assignment.workflow_task and assignment.workflow_task.is_completed) else assignment.workflow_stage_label,
                        "workflow_stage_type": "" if (assignment.workflow_task and assignment.workflow_task.is_completed) else assignment.workflow_stage_type,
                        "response_value": response.response_value if response else "",
                        "response_json": response.response_json if response else {},
                        "review_remark": response.review_remark if response else "",
                        "assignment_id": assignment.id,
                    }
                )
            total_questions += len(question_rows)
            plant_bucket.append(
                {
                    "assignment": _serialize_assignment(assignment, user),
                    "questions": question_rows,
                }
            )

        context["grouped_assignments"] = grouped
        context["assignment_count"] = len(assignments)
        context["question_count"] = total_questions
        context["stage_counts"] = stage_counts
        context["approval_stage_count"] = (
            stage_counts["approval"]
            + stage_counts["pre_final_approval"]
            + stage_counts["final_approval"]
        )
        return context

class AssignmentDetailView(LoginRequiredMixin, TemplateView):
    """
    View for showing all submitted questions for a specific assignment.
    """
    login_url = "accounts:login"
    template_name = "brsr/assignment_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignment_id = kwargs.get('assignment_id')
        user = self.request.user

        # Get the assignment with proper permissions
        assignment = get_object_or_404(
            _assignment_queryset_for_user(user).select_related(
                "plant",
                "section",
                "principle",
                "workflow_template",
                "assignee_content_type",
                "assigner_content_type",
            ).prefetch_related(
                "questions",
                "questions__section",
                "questions__principle",
                "responses",
                "responses__question",
                "responses__documents",
            ),
            pk=assignment_id
        )

        # Ensure workflow task exists
        _ensure_assignment_workflow_task(assignment, current_user=user)

        # Get all questions and their responses
        questions = list(
            assignment.questions.select_related("section", "principle")
            .order_by("display_order", "question_number")
        )

        # Build a map of question_id to response
        responses = {
            response.question_id: response
            for response in assignment.responses.select_related("question")
        }

        question_rows = []
        for question in questions:
            response = responses.get(question.id)

            # Get the response data
            response_value = ""
            response_json = {}
            has_response = False
            answered_by = ""

            if response:
                if response.response_value:
                    response_value = response.response_value
                    has_response = True

                if response.response_json:
                    response_json = response.response_json
                    has_response = True

                if response.answered_by:
                    answered_by = str(response.answered_by)
 
            documents = []
            if response:
                documents = [
                    {
                        "id": doc.id,
                        "name": doc.original_name,
                        "url": doc.document.url,
                    }
                    for doc in response.documents.all()
                ]
 
            question_rows.append({
                "question_id": question.question_id,
                "title": question.question_text,
                "number": question.question_number,
                "question_type": question.question_type,
                "sub_section": question.sub_section or "",
                "options": question.options or [],
                "validation_rules": question.validation_rules or {},
                "status": response.status if response else "draft",
                "status_display": "Final Approved & Locked" if (assignment.workflow_task and assignment.workflow_task.is_completed) else ((response.status if response else "draft").replace("_", " ").title()),
                "workflow_stage": "Final Approved & Locked" if (assignment.workflow_task and assignment.workflow_task.is_completed) else assignment.workflow_stage_label,
                "workflow_stage_type": "" if (assignment.workflow_task and assignment.workflow_task.is_completed) else assignment.workflow_stage_type,
                "response_value": response_value,
                "response_json": response_json,
                "has_response": has_response,
                "answered_by": answered_by,
                "documents": documents,
                "review_remark": response.review_remark if response else "",
                "submitted_by": str(response.submitted_by) if response and response.submitted_by else "",
                "submitted_at": response.submitted_at if response else None,
                "reviewed_by": str(response.reviewed_by) if response and response.reviewed_by else "",
                "reviewed_at": response.reviewed_at if response else None,
                "can_act": self._can_act_on_question(assignment, response, user),
            })

        context["assignment"] = _serialize_assignment(assignment, user)
        context["questions"] = question_rows
 
        # Group questions for display (now grouped correctly, since sub_section is populated)
        context["question_groups"] = self._group_questions(question_rows)
 
        context["questions_json"] = [
            {
                "question_id": q["question_id"],
                "question_number": q["number"],
                "title": q["title"],
                "question_type": q["question_type"],
                "sub_section": q["sub_section"],
                "options": q["options"],
                "validation_rules": q["validation_rules"],
                "response_value": q["response_value"],
                "response_json": q["response_json"],
            }
            for q in question_rows
        ]

        context["question_count"] = len(question_rows)
        context["plant_name"] = assignment.plant.name if assignment.plant_id else ""
        context["company_name"] = getattr(
            getattr(assignment.plant, "created_by", None),
            "company_name",
            ""
        )
        # Counts for summary
        status_counts = {
            "draft": 0,
            "submitted": 0,
            "approved": 0,
            "rejected": 0,
            "resubmitted": 0,
        }
        for q in question_rows:
            status = q.get("status", "draft")
            if status in status_counts:
                status_counts[status] += 1
        context["status_counts"] = status_counts
        context["approval_dashboard_url"] = reverse("brsr:approval_dashboard")
        return context

    def _group_questions(self, questions):
        """Group questions by sub_section or section."""
        groups = {}
        for question in questions:
            key = question.get("sub_section") or "Questions"
            if key not in groups:
                groups[key] = {
                    "label": key,
                    "questions": []
                }
            groups[key]["questions"].append(question)
        if not groups or (len(groups) == 1 and "Questions" in groups):
            return [{"label": "Submitted Responses", "questions": questions}]
        return list(groups.values())

    def _can_act_on_question(self, assignment, response, user):
        """Check if user can act on this question."""
        if not user or not user.is_authenticated:
            return False
        if not assignment or not assignment.workflow_task:
            return False

        task = assignment.workflow_task
        if task.is_completed:
            return False

        stage_type = assignment.workflow_stage_type or (task.current_stage.stage_type if task.current_stage_id else "")
        if stage_type not in {"approval", "pre_final_approval", "final_approval"}:
            return False

        if response and response.status in {"approved", "rejected"}:
            return False

        task_info = _serialize_task_for_user(task, user)
        return bool(task_info and task_info.get("can_act"))


class AssignmentReviewCommentView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "brsr/assignment_review_comments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignment_id = kwargs.get("assignment_id")
        user = self.request.user

        assignment = get_object_or_404(
            _assignment_queryset_for_user(user).select_related(
                "plant",
                "section",
                "principle",
                "workflow_template",
                "assignee_content_type",
                "assigner_content_type",
            ).prefetch_related(
                "questions",
                "questions__section",
                "questions__principle",
                "responses",
                "responses__question",
            ),
            pk=assignment_id,
        )
        _ensure_assignment_workflow_task(assignment, current_user=user)

        questions = list(
            assignment.questions.select_related("section", "principle").order_by("display_order", "question_number")
        )
        responses = {response.question_id: response for response in assignment.responses.select_related("question")}

        task = assignment.workflow_task

        current_stage_type = (
            task.current_stage.stage_type
            if task and task.current_stage
            else ""
        )

        can_review = (
            _is_assigned_reviewer(user, assignment)
            and current_stage_type == "review"
        )
        question_rows = []
        for question in questions:
            response = responses.get(question.id)
            documents = []
            if response:
                documents = [
                    {
                        "id": doc.id,
                        "name": doc.original_name,
                        "url": doc.document.url,
                    }
                    for doc in response.documents.all()
                ]
            question_rows.append(
                {
                    "question_id": question.question_id,
                    "title": question.question_text,
                    "number": question.question_number,
                    "question_type": question.question_type,
                    "options": question.options or [],
                    "validation_rules": question.validation_rules or {},
                    "response_value": response.response_value if response else "",
                    "response_json": response.response_json if response else {},
                    "review_remark": response.review_remark if response else "",
                    "submitted_by": str(response.submitted_by) if response and response.submitted_by else "",
                    "submitted_at": response.submitted_at if response else None,
                    "can_edit_comment": can_review,
                    "reviewed_by": str(response.reviewed_by) if response and response.reviewed_by else "",
                    "reviewed_at": response.reviewed_at if response else None,
                    "documents": documents,
                }
            )

        context["assignment"] = _serialize_assignment(assignment, user)
        context["questions"] = question_rows
        context["questions_json"] = [
            {
                "question_id": q["question_id"],
                "question_type": q["question_type"],
                "options": q["options"],
                "validation_rules": q["validation_rules"],
                "response_value": q["response_value"],
                "response_json": q["response_json"],
            }
            for q in question_rows
        ]

        context["approval_dashboard_url"] = reverse("brsr:approval_dashboard")
        context["assignment_detail_url"] = reverse("brsr:assignment_detail", kwargs={"assignment_id": assignment.id})
        context["question_comment_api_url"] = reverse("brsr:question_comment_api", kwargs={"question_id": "__question__"})
        context["assignment_approve_api_url"] = reverse("brsr:assignment_approve_api", kwargs={"assignment_id": assignment.id})
        context["assignment_reject_api_url"] = reverse("brsr:assignment_reject_api", kwargs={"assignment_id": assignment.id})
        context["is_review_stage"] = assignment.workflow_stage_type == "review"
        context["is_assigned_reviewer"] = _is_assigned_reviewer(user, assignment)
        context["workflow_task"] = _serialize_workflow_task(assignment.workflow_task)
        return context

class BRSRQuestionWorkspaceView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "brsr/brsr_question_workspace.html"

    def _build_context(self, section_code=None, principle_slug=None, question_id=None, assignment_id=None):
        section, principle = _get_section_principle(section_code, principle_slug)
        if not section:
            section = _get_default_section()
        if not section:
            return {"section": None, "principle": None, "questions": [], "topics": []}

        assignment = None
        if assignment_id:
            assignment = (
                Assignment.objects.select_related("plant", "section", "principle", "workflow_template")
                .prefetch_related("questions", "questions__section", "questions__principle", "responses", "responses__documents")
                .filter(pk=assignment_id)
                .first()
            )

        if assignment:
            _ensure_assignment_workflow_task(assignment, current_user=self.request.user)
            questions = list(
                assignment.questions.filter(section=section).select_related("section", "principle", "parent_question").order_by("display_order", "question_number")
            )
            if section.code == "section_c" and principle:
                questions = [question for question in questions if question.principle_id == principle.id]
            elif section.code != "section_c":
                questions = [question for question in questions if question.principle_id is None]
        else:
            questions = list(_question_queryset(section, principle))

        active_question = None
        if question_id:
            active_question = next((q for q in questions if q.question_id == question_id), None)
        if active_question is None and questions:
            active_question = questions[0]

        topics = []
        for question in questions:
            topics.append(
                {
                    "question_id": question.question_id,
                    "title": question.question_text,
                    "question_type": question.question_type,
                    "status": _question_status(question, assignment=assignment),
                    "section_code": question.section.code,
                    "question_number": question.question_number,
                    "help_text": question.help_text or "",
                    "is_required": question.is_required,
                    "display_order": question.display_order,
                    "sub_section": question.sub_section or "",
                    **_question_metadata(question),
                }
            )

        active_question_payload = None
        if active_question:
            response_qs = QuestionResponse.objects.filter(question=active_question)
            if assignment:
                response_qs = response_qs.filter(assignment=assignment)
            response = (response_qs.select_related("assignment").prefetch_related("documents").order_by("-updated_at", "-created_at").first())
            task = assignment.workflow_task if assignment and assignment.workflow_task else (response.workflow_task if response else None)
            documents = []
            if response:
                documents = [
                    {
                        "id": doc.id,
                        "name": doc.original_name,
                        "url": doc.document.url,
                        "uploaded_at": doc.uploaded_at,
                    }
                    for doc in response.documents.all()
                ]
            active_question_payload = {
                "question_id": active_question.question_id,
                "title": active_question.question_text,
                "question_type": active_question.question_type,
                "question_number": active_question.question_number,
                "sub_section": active_question.sub_section or "",
                "help_text": active_question.help_text or "",
                "placeholder_text": active_question.placeholder_text or "",
                "options": active_question.options or [],
                "documents": documents,
                "validation_rules": active_question.validation_rules or {},
                **_question_metadata(active_question),
                "status": response.status if response else "draft",
                "response_json": response.response_json if response else {},
                "response_value": response.response_value if response else "",
                "is_editable": response.is_editable if response else True,
                "assignment_id": response.assignment.assignment_id if response else "",
                "workflow_stage": task.current_stage.label if task and task.current_stage_id else "",
                "workflow_stage_type": task.current_stage.stage_type if task and task.current_stage_id else "",
                "workflow_task": _serialize_workflow_task(task) if task else None,
            }

        section_cards = []
        for sec in _section_scope_queryset():
            section_cards.append(
                    {
                        "code": sec.code,
                        "name": sec.name,
                        "url": reverse("brsr:question_workspace_section", kwargs={"section_code": sec.code}),
                    }
                )

        principle_cards = []
        if section and section.code == "section_c":
            for principle_item in _principle_queryset():
                principle_cards.append(
                    {
                        "slug": principle_item.slug,
                        "name": principle_item.principle_name,
                        "title": principle_item.title,
                        "url": reverse(
                            "brsr:question_workspace_principle",
                            kwargs={"section_code": "section_c", "principle_slug": principle_item.slug},
                        ),
                    }
                )

        question_queryset = BRSRQuestion.objects.filter(id__in=[q.id for q in questions])
        assignment_bundle = _assignment_context(section, principle, question_queryset, assignment=assignment, user=self.request.user)

        return {
            "section": section,
            "principle": principle,
            "assignment": assignment,
            "topics": topics,
            "active_question": active_question_payload,
            "active_question_id": active_question.question_id if active_question else "",
            "active_question_type": active_question.question_type if active_question else "",
            "section_cards": section_cards,
            "principle_cards": principle_cards,
            "counts": _workflow_counts(questions, assignment=assignment),
            **assignment_bundle,
        }

    def get(self, request, section_code=None, principle_slug=None, question_id=None):
        assignment_id = request.GET.get("assignment_id")
        context = self._build_context(section_code, principle_slug, question_id, assignment_id=assignment_id)
        if not context.get("section"):
            messages.info(request, "No active BRSR section found.")
        context["workspace_api_url"] = reverse("brsr:workspace_api")
        context["question_detail_api_url"] = reverse("brsr:question_detail_api", kwargs={"question_id": "__question__"})
        context["question_save_api_url"] = reverse("brsr:question_save_api", kwargs={"question_id": "__question__"})
        context["question_submit_api_url"] = reverse("brsr:question_submit_api", kwargs={"question_id": "__question__"})
        context["question_comment_api_url"] = reverse("brsr:question_comment_api", kwargs={"question_id": "__question__"})
        context["question_approve_api_url"] = reverse("brsr:question_approve_api", kwargs={"question_id": "__question__"})
        context["question_reject_api_url"] = reverse("brsr:question_reject_api", kwargs={"question_id": "__question__"})
        context["assignment_create_api_url"] = reverse("brsr:assignment_create_api")
        context["assignment_options_api_url"] = reverse("brsr:assignment_options_api")
        context["assignment_dashboard_url"] = reverse("brsr:assignment_dashboard")
        context["assignment_id"] = assignment_id or ""
        context["current_section_code"] = section_code if section_code else (context["section"].code if context.get("section") else "")
        context["current_principle_slug"] = principle_slug if principle_slug else (context["principle"].slug if context.get("principle") else "")
        return render(request, self.template_name, context)

    def post(self, request, section_code=None, principle_slug=None, question_id=None):
        assignment_id = request.GET.get("assignment_id")
        context = self._build_context(section_code, principle_slug, question_id, assignment_id=assignment_id)
        active_questions = _pdf_questions_queryset().filter(section=context["section"])
        if context["principle"]:
            active_questions = active_questions.filter(principle=context["principle"])
        else:
            active_questions = active_questions.filter(principle__isnull=True)

        form = BRSRAssignmentForm(
            request.POST,
            plant_queryset=_company_scope_plants(self.request.user),
            user_queryset=User.objects.filter(is_active=True).select_related("role", "department").order_by(
                "full_name", "username"
            ),
            question_queryset=active_questions,
            financial_year_queryset=FinancialYear.objects.all().order_by("-start_date"),
        )
        if form.is_valid():
            selected_questions = form.cleaned_data["question_ids"]
            try:
                assignment = _create_brsr_assignment(
                    user=self.request.user,
                    section=context["section"],
                    principle=context["principle"],
                    cleaned_data=form.cleaned_data,
                    question_queryset=selected_questions,
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
                context.update(
                    {
                        "workspace_api_url": reverse("brsr:workspace_api"),
                        "question_detail_api_url": reverse("brsr:question_detail_api", kwargs={"question_id": "__question__"}),
                        "question_save_api_url": reverse("brsr:question_save_api", kwargs={"question_id": "__question__"}),
                        "question_submit_api_url": reverse("brsr:question_submit_api", kwargs={"question_id": "__question__"}),
                        "question_comment_api_url": reverse("brsr:question_comment_api", kwargs={"question_id": "__question__"}),
                        "question_approve_api_url": reverse("brsr:question_approve_api", kwargs={"question_id": "__question__"}),
                        "question_reject_api_url": reverse("brsr:question_reject_api", kwargs={"question_id": "__question__"}),
                        "assignment_create_api_url": reverse("brsr:assignment_create_api"),
                        "assignment_options_api_url": reverse("brsr:assignment_options_api"),
                        "assignment_dashboard_url": reverse("brsr:assignment_dashboard"),
                        "assignment_form": form,
                        "current_section_code": section_code if section_code else (context["section"].code if context.get("section") else ""),
                        "current_principle_slug": principle_slug if principle_slug else (context["principle"].slug if context.get("principle") else ""),
                    }
                )
                return render(request, self.template_name, context)
            messages.success(
                request,
                f"Assignment {assignment.assignment_id} created for {selected_questions.count()} questions.",
            )
            return redirect(
                reverse(
                    "brsr:question_workspace_section",
                    kwargs={"section_code": context["section"].code},
                )
            )

        context.update(
            {
                "workspace_api_url": reverse("brsr:workspace_api"),
                "question_detail_api_url": reverse("brsr:question_detail_api", kwargs={"question_id": "__question__"}),
                "question_save_api_url": reverse("brsr:question_save_api", kwargs={"question_id": "__question__"}),
                "question_submit_api_url": reverse("brsr:question_submit_api", kwargs={"question_id": "__question__"}),
                "question_comment_api_url": reverse("brsr:question_comment_api", kwargs={"question_id": "__question__"}),
                "question_approve_api_url": reverse("brsr:question_approve_api", kwargs={"question_id": "__question__"}),
                "question_reject_api_url": reverse("brsr:question_reject_api", kwargs={"question_id": "__question__"}),
                "assignment_create_api_url": reverse("brsr:assignment_create_api"),
                "assignment_options_api_url": reverse("brsr:assignment_options_api"),
                "assignment_dashboard_url": reverse("brsr:assignment_dashboard"),
                "assignment_form": form,
                "current_section_code": section_code if section_code else (context["section"].code if context.get("section") else ""),
                "current_principle_slug": principle_slug if principle_slug else (context["principle"].slug if context.get("principle") else ""),
            }
        )
        return render(request, self.template_name, context)


def brsr_list(request):
    return BRSRDashboardView.as_view()(request)


def brsr_workspace(request, section_code=None, principle_slug=None, question_id=None):
    return BRSRQuestionWorkspaceView.as_view()(request, section_code=section_code, principle_slug=principle_slug, question_id=question_id)
