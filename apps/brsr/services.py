"""
Frequency-based automatic assignment — generation service.

This module owns ALL of the period math (financial year, quarters, weeks)
and the duplicate-prevention check. It does NOT duplicate any assignment-
creation or workflow logic — every generated Assignment is created by
calling the existing `_create_brsr_assignment` from views.py, so a
scheduled assignment is byte-for-byte the same kind of object a human
creates manually (same workflow start, same reviewer linking, same
QuestionResponse seeding).
AssignmentSchedule --> [this module] --> Assignment --> Workflow --> QuestionResponse
"""
import logging
from calendar import month_abbr
from datetime import date, timedelta
from django.utils import timezone
from .models import Assignment, AssignmentSchedule

logger = logging.getLogger(__name__)

MONTH_ABBR = {i: month_abbr[i].upper() for i in range(1, 13)}

# Calendar month a given quarter STARTS in (BRSR / Indian FY quarters).
QUARTER_START_MONTHS = {'Q1': 4, 'Q2': 7, 'Q3': 10, 'Q4': 1}


# ---------------------------------------------------------------------------
# Period math
# ---------------------------------------------------------------------------

def financial_year_for_date(d: date) -> str:
    """BRSR financial year runs April -> March, e.g. 2026-2027."""
    if d.month >= 4:
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


def quarter_for_date(d: date) -> str:
    if d.month in (4, 5, 6):
        return 'Q1'
    if d.month in (7, 8, 9):
        return 'Q2'
    if d.month in (10, 11, 12):
        return 'Q3'
    return 'Q4'  # Jan-Mar


def quarter_start_date(quarter_code: str, today: date) -> date:
    """Resolve the calendar start date of `quarter_code` for the financial
    year that `today` currently sits in."""
    month = QUARTER_START_MONTHS[quarter_code]
    year = today.year
    if month == 1 and today.month >= 4:
        # Q4 (Jan) of the FY that started this calendar year falls next year.
        year += 1
    elif month != 1 and today.month < 4:
        # We're in Jan-Mar, so this FY's Q1/Q2/Q3 happened last calendar year.
        year -= 1
    return date(year, month, 1)


def week_period_code(d: date) -> str:
    return f"Week-{d.isocalendar()[1]}"


def _period_due_date(schedule: AssignmentSchedule, trigger_date: date):
    """Best-effort due date for the generated Assignment, based on the
    schedule's own configuration. Never required for generation to
    succeed — falls back to None (no due date) if it can't be computed."""
    if schedule.frequency == 'weekly' and schedule.weekly_end_day is not None and schedule.weekly_start_day is not None:
        delta_days = (schedule.weekly_end_day - schedule.weekly_start_day) % 7
        return trigger_date + timedelta(days=delta_days)
    if schedule.frequency == 'monthly':
        next_month = trigger_date.replace(day=28) + timedelta(days=4)
        return next_month - timedelta(days=next_month.day)
    if schedule.frequency == 'quarterly':
        return trigger_date + timedelta(days=89)
    return None


# ---------------------------------------------------------------------------
# Duplicate prevention
# ---------------------------------------------------------------------------

def assignment_exists_for_period(schedule: AssignmentSchedule, financial_year: str, period_code: str) -> bool:
    """
    True if an Assignment has already been generated for this exact
    (schedule, financial_year, period_code) combination. This is the
    application-level half of duplicate prevention; a partial unique
    constraint on Assignment enforces the same rule at the DB level.
    """
    return Assignment.objects.filter(
        schedule=schedule, financial_year=financial_year, period_code=period_code
    ).exists()


# ---------------------------------------------------------------------------
# Which periods are due today, for a given schedule
# ---------------------------------------------------------------------------

def due_periods_for_schedule(schedule, today: date):
    """
    Returns a list of (financial_year, period_code, period_label) tuples
    that are due to be generated *today* for `schedule`. Empty list means
    nothing to do today. Pure function over duck-typed schedule attributes
    (frequency, weekly_start_day, selected_months, selected_quarters,
    financial_year) so it's independently unit-testable without the ORM.
    """
    periods = []
    fy = financial_year_for_date(today)

    if schedule.frequency == 'weekly':
        if schedule.weekly_start_day is not None and today.weekday() == schedule.weekly_start_day:
            code = week_period_code(today)
            periods.append((fy, code, code))

    elif schedule.frequency == 'monthly':
        if today.day == 1 and today.month in (schedule.selected_months or []):
            code = MONTH_ABBR[today.month]
            periods.append((fy, code, code))

    elif schedule.frequency == 'quarterly':
        for quarter_code in (schedule.selected_quarters or []):
            if quarter_code not in QUARTER_START_MONTHS:
                continue
            if today == quarter_start_date(quarter_code, today):
                periods.append((fy, quarter_code, quarter_code))

    elif schedule.frequency == 'annually':
        target_fy = schedule.financial_year or fy
        periods.append((target_fy, 'ANNUAL', f"FY{target_fy}"))

    return periods


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def create_assignment_from_schedule(schedule: AssignmentSchedule, financial_year: str,
                                     period_code: str, period_label: str, trigger_date: date):
    """
    Turns one due (schedule, period) pair into a real Assignment, reusing
    the existing manual-assignment creation path so workflow start,
    reviewer linking, and QuestionResponse seeding are identical to a
    manually created assignment. Returns None (no-op) if this period was
    already generated.
    """
    # Local import avoids a circular import between views.py <-> this module.
    from .views import _create_brsr_assignment

    if assignment_exists_for_period(schedule, financial_year, period_code):
        return None

    if schedule.created_by_id is None:
        logger.warning(
            "AssignmentSchedule %s has no created_by set; skipping generation "
            "for period %s (an assigner is required).", schedule.schedule_id, period_code,
        )
        return None

    cleaned_data = {
        "plant": schedule.plant,
        "financial_year": financial_year,
        "assignee": schedule.assignee,
        "reviewer": schedule.reviewer,
        "priority": schedule.priority,
        "notes": schedule.notes,
        "due_date": _period_due_date(schedule, trigger_date),
        "data_collection_frequency": schedule.frequency,
        "assigner": schedule.created_by,
    }

    assignment = _create_brsr_assignment(
        user=schedule.created_by,
        section=schedule.section,
        principle=schedule.principle,
        cleaned_data=cleaned_data,
        question_queryset=schedule.questions.all(),
        workflow_template_override=schedule.workflow_template,
    )
    assignment.schedule = schedule
    assignment.period_code = period_code
    assignment.period_label = period_label
    assignment.save(update_fields=["schedule", "period_code", "period_label", "updated_at"])
    return assignment


def run_daily_schedule_generation(today=None):
    """
    Entry point for the Celery Beat task (see tasks.py). Iterates every
    active AssignmentSchedule, works out what's due today, and generates
    assignments — skipping anything already generated for that
    schedule/FY/period. A failure on one schedule is logged and does not
    stop the rest from being processed.
    """
    today = today or timezone.localdate()
    created = []

    schedules = AssignmentSchedule.objects.filter(is_active=True).select_related(
        "plant", "section", "principle", "workflow_template"
    )
    for schedule in schedules:
        try:
            for financial_year, period_code, period_label in due_periods_for_schedule(schedule, today):
                assignment = create_assignment_from_schedule(
                    schedule, financial_year, period_code, period_label, trigger_date=today
                )
                if assignment is not None:
                    created.append(assignment)
        except Exception:
            logger.exception(
                "Failed to generate assignment(s) for schedule %s", schedule.schedule_id
            )
            continue

    return created