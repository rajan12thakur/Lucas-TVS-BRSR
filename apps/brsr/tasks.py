import logging
from celery import shared_task
from .services import run_daily_schedule_generation

logger = logging.getLogger(__name__)


@shared_task(name="brsr.generate_scheduled_assignments")
def generate_scheduled_assignments():
    """
    Daily Celery Beat task. Walks every active AssignmentSchedule, works
    out which ones are due today, and creates the corresponding Assignment
    through the existing assignment-creation + workflow-start path.

    Idempotent: safe to run more than once on the same day (e.g. a manual
    trigger, or a beat misfire) — duplicate assignments are never created,
    see schedule_services.assignment_exists_for_period and the partial
    unique constraint on Assignment(schedule, financial_year, period_code).
    """
    created = run_daily_schedule_generation()
    logger.info("Generated %s scheduled BRSR assignment(s): %s",
                len(created), [a.assignment_id for a in created])
    return [a.assignment_id for a in created]