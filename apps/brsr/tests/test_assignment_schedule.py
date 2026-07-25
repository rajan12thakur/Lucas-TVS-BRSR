"""
Two layers, matching the testing strategy doc:

  1. Pure period-math unit tests — no DB, no fixtures. `due_periods_for_schedule`
     is a pure function over duck-typed attributes, so it's tested against a
     lightweight stub instead of a real AssignmentSchedule row.

  2. Integration tests — real models, exercising duplicate prevention and
     the full schedule -> Assignment -> workflow path. The setUp() below
     creates the minimum graph of objects (Plant, BRSRSection, User,
     ApprovalConfigurationTemplate + one stage) needed to satisfy
     _create_brsr_assignment's requirements. Field names/kwargs for
     Plant / ApprovalConfigurationTemplate / ApprovalConfigurationStage
     are assumed from usage in views.py — adjust to match your actual
     model signatures/required fields if they differ (e.g. if Plant or
     the workflow template require additional mandatory fields such as
     `created_by`, `company`, etc. in your project).
"""
from datetime import date
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.brsr.models import Assignment, AssignmentSchedule, BRSRQuestion, BRSRSection
from apps.brsr.services import (
    due_periods_for_schedule,
    financial_year_for_date,
    quarter_for_date,
    quarter_start_date,
    run_daily_schedule_generation,
    week_period_code,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# 1. Pure period-math tests (no DB)
# ---------------------------------------------------------------------------

class PeriodMathTests(TestCase):
    def test_financial_year_before_april_belongs_to_previous_fy(self):
        self.assertEqual(financial_year_for_date(date(2027, 3, 31)), "2026-2027")

    def test_financial_year_from_april_starts_new_fy(self):
        self.assertEqual(financial_year_for_date(date(2026, 4, 1)), "2026-2027")

    def test_quarter_for_date_boundaries(self):
        self.assertEqual(quarter_for_date(date(2026, 4, 1)), "Q1")
        self.assertEqual(quarter_for_date(date(2026, 6, 30)), "Q1")
        self.assertEqual(quarter_for_date(date(2026, 7, 1)), "Q2")
        self.assertEqual(quarter_for_date(date(2026, 10, 1)), "Q3")
        self.assertEqual(quarter_for_date(date(2027, 1, 1)), "Q4")
        self.assertEqual(quarter_for_date(date(2027, 3, 31)), "Q4")

    def test_quarter_start_date_q4_rolls_into_next_calendar_year(self):
        # Today sits in Q3 (FY 2026-2027); Q4 of the SAME fy starts Jan 2027.
        today = date(2026, 11, 15)
        self.assertEqual(quarter_start_date("Q4", today), date(2027, 1, 1))

    def test_quarter_start_date_q1_rolls_back_when_today_is_in_jan_mar(self):
        # Today sits in Q4 (Feb 2027, FY 2026-2027); Q1 of same fy was Apr 2026.
        today = date(2027, 2, 10)
        self.assertEqual(quarter_start_date("Q1", today), date(2026, 4, 1))

    def test_week_period_code_format(self):
        # ISO week 15 of 2026 falls in April.
        d = date.fromisocalendar(2026, 15, 1)
        self.assertEqual(week_period_code(d), "Week-15")


class DuePeriodsForScheduleTests(TestCase):
    """due_periods_for_schedule only reads attributes off `schedule`, so a
    SimpleNamespace stub is enough — no ORM needed."""

    def _stub(self, **overrides):
        base = dict(
            frequency="weekly",
            weekly_start_day=None,
            selected_months=[],
            selected_quarters=[],
            financial_year="",
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_weekly_due_only_on_start_day(self):
        schedule = self._stub(frequency="weekly", weekly_start_day=0)  # Monday
        monday = date(2026, 8, 3)     # a Monday
        tuesday = date(2026, 8, 4)

        self.assertEqual(len(due_periods_for_schedule(schedule, monday)), 1)
        self.assertEqual(due_periods_for_schedule(schedule, tuesday), [])

    def test_monthly_due_only_on_1st_of_selected_months(self):
        schedule = self._stub(frequency="monthly", selected_months=[4, 10])
        self.assertEqual(len(due_periods_for_schedule(schedule, date(2026, 4, 1))), 1)
        self.assertEqual(due_periods_for_schedule(schedule, date(2026, 5, 1)), [])   # not selected
        self.assertEqual(due_periods_for_schedule(schedule, date(2026, 4, 2)), [])   # not the 1st

        fy, code, label = due_periods_for_schedule(schedule, date(2026, 4, 1))[0]
        self.assertEqual(code, "APR")

    def test_quarterly_due_only_at_quarter_start(self):
        schedule = self._stub(frequency="quarterly", selected_quarters=["Q1", "Q3"])
        self.assertEqual(len(due_periods_for_schedule(schedule, date(2026, 4, 1))), 1)   # Q1 start
        self.assertEqual(due_periods_for_schedule(schedule, date(2026, 7, 1)), [])       # Q2 not selected
        self.assertEqual(len(due_periods_for_schedule(schedule, date(2026, 10, 1))), 1)  # Q3 start
        self.assertEqual(due_periods_for_schedule(schedule, date(2026, 10, 2)), [])      # mid-quarter

    def test_annual_is_always_due_relies_on_duplicate_prevention(self):
        schedule = self._stub(frequency="annually", financial_year="2026-2027")
        periods = due_periods_for_schedule(schedule, date(2026, 6, 15))
        self.assertEqual(periods, [("2026-2027", "ANNUAL", "FY2026-2027")])


# ---------------------------------------------------------------------------
# 2. Integration tests — adjust fixtures below to match your project's
#    actual required fields for Plant / ApprovalConfigurationTemplate.
# ---------------------------------------------------------------------------

class ScheduleGenerationIntegrationTests(TestCase):
    def setUp(self):
        from apps.organizations.models import (
            ApprovalConfigurationTemplate, ApprovalConfigurationStage, Plant,
        )

        self.admin = User.objects.create_user(username="admin", password="x", is_superuser=True)
        self.assignee = User.objects.create_user(username="assignee", password="x")

        self.plant = Plant.objects.create(name="Test Plant", code="TST", is_active=True)

        self.section = BRSRSection.objects.create(code="section_a", name="General Disclosures", display_order=1)
        self.question = BRSRQuestion.objects.create(
            question_id="a_q1", section=self.section, question_text="Test question",
            question_number="1", question_type="text",
        )

        self.template = ApprovalConfigurationTemplate.objects.create(
            name="BRSR Test Template", framework="BRSR", is_active=True,
        )
        ApprovalConfigurationStage.objects.create(
            template=self.template, label="Data Entry", stage_type="data_entry", level=1,
        )

    def _create_schedule(self, **overrides):
        defaults = dict(
            name="Test Schedule",
            plant=self.plant,
            section=self.section,
            financial_year="2026-2027",
            workflow_template=self.template,
            frequency="monthly",
            selected_months=[4],
            priority="medium",
            created_by=self.admin,
            assignee_content_type=ContentType.objects.get_for_model(User),
            assignee_object_id=self.assignee.pk,
        )
        defaults.update(overrides)
        schedule = AssignmentSchedule.objects.create(**defaults)
        schedule.questions.set([self.question])
        return schedule

    def test_generates_assignment_on_due_date(self):
        self._create_schedule()
        created = run_daily_schedule_generation(today=date(2026, 4, 1))
        self.assertEqual(len(created), 1)
        assignment = created[0]
        self.assertEqual(assignment.period_code, "APR")
        self.assertEqual(assignment.financial_year, "2026-2027")
        self.assertEqual(list(assignment.questions.all()), [self.question])

    def test_no_assignment_generated_on_non_due_date(self):
        self._create_schedule()
        created = run_daily_schedule_generation(today=date(2026, 4, 2))
        self.assertEqual(created, [])

    def test_duplicate_prevention_running_twice_same_day(self):
        self._create_schedule()
        first = run_daily_schedule_generation(today=date(2026, 4, 1))
        second = run_daily_schedule_generation(today=date(2026, 4, 1))
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(Assignment.objects.filter(period_code="APR").count(), 1)

    def test_inactive_schedule_is_skipped(self):
        self._create_schedule(is_active=False)
        created = run_daily_schedule_generation(today=date(2026, 4, 1))
        self.assertEqual(created, [])

    def test_annual_generates_exactly_once_across_many_runs(self):
        self._create_schedule(frequency="annually", selected_months=[], financial_year="2026-2027")
        run_daily_schedule_generation(today=date(2026, 5, 1))
        run_daily_schedule_generation(today=date(2026, 6, 1))
        run_daily_schedule_generation(today=date(2026, 7, 1))
        self.assertEqual(Assignment.objects.filter(period_code="ANNUAL").count(), 1)