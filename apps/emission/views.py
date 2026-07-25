from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views import View
from django.urls import reverse_lazy
from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime
import json
from django.views.generic import (ListView,CreateView,UpdateView,DeleteView,)
from .models import EmissionTransaction
from .forms import EmissionTransactionForm
from .models import *
from django.shortcuts import get_object_or_404
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification,Timesheet


class EmissionsDashboardView(TemplateView):
    """
    Renders the main Carbon Emissions Dashboard page
    (KPI cards, monthly trend, scope breakdown, by-plant chart,
    task status, recent activity).
    """
    template_name = "emission/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["kpis"] = [
            {"label": "TOTAL EMISSIONS YTD", "value": 50276, "unit": "tCO2e",
             "delta": -4.2, "accent": "green"},
            {"label": "SCOPE 1 DIRECT", "value": 14470, "unit": "tCO2e",
             "delta": -2.1, "accent": "teal"},
            {"label": "SCOPE 2 INDIRECT", "value": 10266, "unit": "tCO2e",
             "delta": -6.8, "accent": "blue"},
            {"label": "SCOPE 3 VALUE CHAIN", "value": 25540, "unit": "tCO2e",
             "delta": 1.3, "accent": "orange"},
        ]

        context["months"] = ["Apr", "May", "Jun", "Jul", "Aug", "Sep",
                              "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
        context["scope1_series"] = [1420, 1390, 1350, 1300, 1480, 1550,
                                     1500, 1380, 1300, 1250, 1300, 1400]
        context["scope2_series"] = [980, 950, 900, 870, 1000, 1050,
                                     1000, 910, 860, 830, 870, 930]
        context["scope3_series"] = [2450, 2380, 2300, 2250, 2500, 2600,
                                     2550, 2300, 2200, 2150, 2250, 2400]

        context["scope_breakdown"] = [
            {"name": "Scope 1", "value": 14470, "pct": 28.8, "color": "#22c07a"},
            {"name": "Scope 2", "value": 10266, "pct": 20.4, "color": "#17b6a7"},
            {"name": "Scope 3", "value": 25540, "pct": 50.8, "color": "#3b6df0"},
        ]

        context["by_plant"] = [
            {"name": "Mundra", "value": 8600},
            {"name": "Tiroda", "value": 8100},
            {"name": "Raipur", "value": 7300},
            {"name": "Kawai", "value": 6600},
            {"name": "Udupi", "value": 5900},
        ]

        context["task_status"] = {
            "total": 142,
            "completed": 98,
            "pending_review": 23,
            "overdue": 7,
        }

        context["recent_activity"] = [
            {"status": "ok", "title": "Q3 Diesel Consumption — Mundra Plant",
             "author": "Priya Sharma", "meta": "2h ago"},
            {"status": "warn", "title": "Nov Grid Electricity — Tiroda Plant",
             "author": "Rahul Mehta", "meta": "3d overdue"},
            {"status": "pending", "title": "Business Travel — Q3 FY25",
             "author": "Neha Gupta", "meta": "5h ago"},
            {"status": "warn", "title": "Refrigerant Leakage — Raipur Plant",
             "author": "Amit Singh", "meta": "1d ago"},
            {"status": "ok", "title": "Water Withdrawal — Kawai Plant",
             "author": "Sunita Rao", "meta": "6h ago"},
        ]

        return context


class EmissionsDashboardDataView(View):
    """
    Optional JSON endpoint — same data as above, useful if the front end
    (e.g. the Chart.js widgets) wants to fetch/refresh the dashboard via AJAX
    instead of relying purely on server-rendered context.
    """

    def get(self, request, *args, **kwargs):
        data = {
            "kpis": {
                "total_ytd": 50276,
                "scope1": 14470,
                "scope2": 10266,
                "scope3": 25540,
            },
            "monthly_trend": {
                "months": ["Apr", "May", "Jun", "Jul", "Aug", "Sep",
                           "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"],
                "scope1": [1420, 1390, 1350, 1300, 1480, 1550,
                          1500, 1380, 1300, 1250, 1300, 1400],
                "scope2": [980, 950, 900, 870, 1000, 1050,
                          1000, 910, 860, 830, 870, 930],
                "scope3": [2450, 2380, 2300, 2250, 2500, 2600,
                          2550, 2300, 2200, 2150, 2250, 2400],
            },
            "by_plant": [
                {"name": "Mundra", "value": 8600},
                {"name": "Tiroda", "value": 8100},
                {"name": "Raipur", "value": 7300},
                {"name": "Kawai", "value": 6600},
                {"name": "Udupi", "value": 5900},
            ],
            "task_status": {
                "total": 142, "completed": 98,
                "pending_review": 23, "overdue": 7,
            },
        }
        return JsonResponse(data)




from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import request, status

from django.db import transaction
from django.utils import timezone

from apps.emission.models import EmissionAssignment, EmissionAssignmentSource


def generate_assignment_code():
    """
    Generate Assignment Code
    Example:
    EA000001
    EA000002
    """

    last_assignment = (
        EmissionAssignment.objects
        .order_by("-id")
        .first()
    )

    if last_assignment:

        try:
            last_number = int(
                last_assignment.assignment_code.replace("EA", "")
            )
        except:
            last_number = last_assignment.id

        next_number = last_number + 1

    else:
        next_number = 1

    return f"EA{next_number:06d}"





from django.views.generic import TemplateView
from django.db.models import Q
from django.utils import timezone

from .models import EmissionAssignment


# views.py

class EmissionAssignmentDashboardView(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "emission/assignment.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the user from the request
        user = self.request.user
        
        # Get assignment_id from URL parameters
        assignment_id = self.request.GET.get('assignment')
        
        # Get all assignments
        assignments = (
            EmissionAssignment.objects
            .select_related(
                "company",
                "plant",
                "financial_year",
                "financial_month",
                "scope",
                "assignee",
                "assigner",
            )
            .prefetch_related(
                "transactions",
                "assignment_sources__source__activity",
            )
            .order_by('-created_at')
        )
        
        # Validate assignment_id
        highlight_assignment_id = None
        if assignment_id:
            try:
                assignments.get(id=assignment_id)
                highlight_assignment_id = assignment_id
            except EmissionAssignment.DoesNotExist:
                pass
        
        # ====== GET ALL TIMESHEETS (including completed, overdue, rejected) ======
        timesheets = Timesheet.objects.filter(
            models.Q(user=user) | 
            models.Q(assignment__assignee=user)
        ).select_related('assignment', 'company', 'user').order_by('-created_at')[:10]
        
        # ====== COUNT ONLY UNREAD for the badge (assigned and viewed) ======
        timesheet_count = Timesheet.objects.filter(
            models.Q(user=user) | 
            models.Q(assignment__assignee=user)
        ).filter(
            models.Q(status='assigned') | models.Q(status='viewed')
        ).count()
        
        # ====== GET NOTIFICATIONS ======
        # Get ALL notifications (read and unread) for the dropdown
        navbar_notifications = Notification.objects.filter(
            recipient=user
        ).exclude(
            title__icontains='Timesheet'
        ).order_by('-created_at')[:10]
        
        # Count ONLY unread for the badge
        navbar_notification_count = Notification.objects.filter(
            recipient=user,
            is_read=False
        ).exclude(
            title__icontains='Timesheet'
        ).count()
        
        # Get stats
        today = timezone.now().date()
        assignment_stats = {
            "assignment_count": assignments.count(),
            "open_count": assignments.filter(
                status__in=["ASSIGNED", "IN_PROGRESS", "SUBMITTED"]
            ).count(),
            "completed_count": assignments.filter(status="APPROVED").count(),
            "overdue_count": assignments.filter(
                due_date__lt=today
            ).exclude(status="APPROVED").count(),
        }
        
        # Update context
        context.update({
            "assignments": assignments,
            "assignment_scope": "ALL ASSIGNMENTS",
            "highlight_assignment_id": highlight_assignment_id,
            "timesheets": timesheets,  # ALL timesheets
            "timesheet_count": timesheet_count,  # Only unread count
            "navbar_notifications": navbar_notifications,
            "navbar_notification_count": navbar_notification_count,
            **assignment_stats,
        })
        
        return context

class SaveEmissionAssignmentAPIView(APIView):

    @transaction.atomic
    def post(self, request):

        data = request.data

        try:

            # ----------------------------------------
            # Check if Assignment already exists
            # ----------------------------------------
            existing = EmissionAssignment.objects.filter(
                company_id=data.get("company"),
                plant_id=data.get("plant"),
                financial_year_id=data.get("financial_year"),
                financial_month_id=data.get("financial_month"),
                scope_id=data.get("scope_id"),
            ).first()

            if existing:
                return Response(
                    {
                        "success": False,
                        "message": "This scope is already assigned."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ----------------------------------------
            # Create Assignment
            # ----------------------------------------
            assignment = EmissionAssignment.objects.create(

                assignment_code=generate_assignment_code(),

                company_id=data.get("company"),

                plant_id=data.get("plant"),

                financial_year_id=data.get("financial_year"),

                financial_month_id=data.get("financial_month"),

                scope_id=data.get("scope_id"),

                assignee_id=data.get("assignee"),

                assigner=request.user,

                due_date=data.get("due_date"),

                priority=data.get("priority"),

                notes=data.get("notes"),

                status="ASSIGNED",

            )

            source_ids = data.get("source_ids", [])

            for source_id in source_ids:

                EmissionAssignmentSource.objects.create(

                    assignment=assignment,

                    source_id=source_id,

                )

            # ----------------------------------------
            # Create Notification
            # ----------------------------------------
            NotificationService.notify(event="ASSIGN_SCOPE",assignment=assignment,sender=request.user,)

            return Response(
                {
                    "success": True,
                    "message": "Assignment created successfully.",
                    "assignment_id": assignment.id,
                    "assignment_code": assignment.assignment_code,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:

            return Response(
                {
                    "success": False,
                    "message": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class ESGDisclosureView(TemplateView):
    """
    View to display ESG / BRSR Disclosure page.
    """
    template_name = 'emission/report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_year'] = datetime.now().year
        return context





from .models import (
    EmissionTransaction,
    EmissionScope,
    EmissionCategory,
)

from apps.companies.models import Company
from apps.organizations.models import (
    Plant,
    FinancialYear,
    FinancialMonth,
)
from .models import EmissionAssignment
from django.utils import timezone
from ..organizations.models import FinancialYear, FinancialMonth
from django.core.exceptions import PermissionDenied

class ScopeDashboardView(ListView):

    model = EmissionTransaction

    template_name = "emission/scope_dataentry.html"

    context_object_name = "transactions"

    paginate_by = 20

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        assignment_id = self.request.GET.get("assignment")

        assignment = None

        if assignment_id:

            assignment = (
                EmissionAssignment.objects
                .select_related(
                    "company",
                    "plant",
                    "financial_year",
                    "financial_month",
                    "scope",
                    "assigner",
                    "assignee",
                )
                .prefetch_related(
                    "assignment_sources__source",
                )
                .filter(id=assignment_id)
                .first()
            )

            if not assignment:
                raise PermissionDenied("Assignment not found.")

            # --------------------------------------------------
            # Access Control
            # --------------------------------------------------
            is_assignee = assignment.assignee == self.request.user
            is_assigner = assignment.assigner == self.request.user

            # Change this according to your Role model
            is_reviewer = (
                hasattr(self.request.user, "role")
                and self.request.user.role
                and self.request.user.role.role_code == "REVIEWER"
            )

            if not (is_assignee or is_assigner or is_reviewer):
                raise PermissionDenied("You are not authorized to access this assignment.")

        context["assignment"] = assignment

        context["is_review_mode"] = (assignment is not None and assignment.status == "SUBMITTED")

        context["is_assignee"] = (
            assignment is not None
            and assignment.assignee == self.request.user
        )

        context["is_assigner"] = (
            assignment is not None
            and assignment.assigner == self.request.user
        )

        context["is_reviewer"] = (
            assignment is not None
            and hasattr(self.request.user, "role")
            and self.request.user.role
            and self.request.user.role.role_code == "REVIEWER"
        )

        

        if assignment:
            scope = (
                EmissionScope.objects
                .prefetch_related("categories")
                .get(id=assignment.scope_id)
            )
        else:
            scope = (
                EmissionScope.objects
                .prefetch_related("categories")
                .get(code="S1")
            )

        context["scope"] = scope

        if assignment:

            category_ids = (assignment.assignment_sources.values_list("source__activity__category_id",flat=True).distinct())

            context["categories"] = (scope.categories.filter(id__in=category_ids,is_active=True,).order_by("display_order"))

        else:

            context["categories"] = (
                scope.categories
                .filter(is_active=True)
                .order_by("display_order")
            )

        context["companies"] = Company.objects.filter(
            is_active=True
        ).order_by(
            "company_name"
        )

        context["plants"] = Plant.objects.filter(is_active=True).order_by("name")

        context["financial_years"] = FinancialYear.objects.all()

        context["financial_months"] = (
            FinancialMonth.objects
            .filter(is_active=True)
            .order_by("display_order")
        )

        today = timezone.now().date()

        current_financial_year = (
            FinancialYear.objects.filter(
                start_date__lte=today,
                end_date__gte=today
            ).first()
        )

        current_month_number = today.month

        # Convert calendar month to your financial month numbering
        month_mapping = {
            4: 1,   # April
            5: 2,
            6: 3,
            7: 4,
            8: 5,
            9: 6,
            10: 7,
            11: 8,
            12: 9,
            1: 10,
            2: 11,
            3: 12,
        }

        current_financial_month = FinancialMonth.objects.filter(
            month_number=month_mapping[current_month_number]
        ).first()

        context["current_financial_year"] = current_financial_year
        context["current_financial_month"] = current_financial_month
        context["is_assignment_locked"] = (assignment is not None and assignment.status == "SUBMITTED")

        return context
    


from django.http import JsonResponse
from django.views import View

from .models import (
    EmissionActivity,
    EmissionSource,
)


class CategoryActivitiesView(View):

    def get(self, request, *args, **kwargs):

        category_id = request.GET.get("category_id")
        assignment_id = request.GET.get("assignment")

        assignment = None
        assigned_source_ids = []

        if assignment_id:

            assignment = (
                EmissionAssignment.objects
                .prefetch_related("assignment_sources")
                .filter(id=assignment_id)
                .first()
            )

            if assignment:

                is_assignee = assignment.assignee == request.user
                is_assigner = assignment.assigner == request.user

                is_reviewer = (
                    hasattr(request.user, "role")
                    and request.user.role
                    and request.user.role.role_code == "REVIEWER"
                )

                if not (is_assignee or is_assigner or is_reviewer):
                    return JsonResponse({"activities": []})

                assigned_source_ids = list(
                    assignment.assignment_sources.values_list(
                        "source_id",
                        flat=True,
                    )
                )

        activities = (
            EmissionActivity.objects.filter(
                category_id=category_id,
                is_active=True,
            )
            .select_related(
                "base_unit",
            )
            .prefetch_related(
                "sources",
            )
            .order_by(
                "display_order",
            )
        )

        data = []

        for activity in activities:

            sources = []

            if assignment_id:

                source_queryset = (
                    activity.sources.filter(
                        id__in=assigned_source_ids,
                        is_active=True,
                    ).order_by("display_order")
                )

            else:

                source_queryset = (
                    activity.sources.filter(
                        is_active=True,
                    ).order_by("display_order")
                )

            for source in source_queryset:

                sources.append(
                    {
                        "id": source.id,
                        "code": source.source_code,
                        "name": source.source_name,
                    }
                )
            if assignment and not sources:
                continue
            data.append(
                {
                    "id": activity.id,
                    "code": activity.code,
                    "name": activity.name,
                    "unit": activity.base_unit.symbol,
                    "base_unit_id": activity.base_unit.id,
                    "sources": sources,
                }
            )

        return JsonResponse(
            {
                "activities": data,
            }
        )
    




from django.utils import timezone

from .models import (
    EmissionFactor,
)


class ActivityFactorView(View):

    def get(self, request, *args, **kwargs):

        activity_id = request.GET.get("activity_id")

        factor = (
            EmissionFactor.objects
            .select_related(
                "unit",
            )
            .filter(
                activity_id=activity_id,
                is_active=True,
                effective_from__lte=timezone.now().date(),
            )
            .order_by(
                "-effective_from",
            )
            .first()
        )

        if not factor:

            return JsonResponse(
                {
                    "success": False,
                    "message": "Emission factor not found.",
                }
            )

        return JsonResponse(
            {
                "success": True,
                "factor": str(factor.emission_factor),
                "unit": factor.unit.symbol,
                "source": factor.source,
                "factor_id": factor.id,
            }
        )



from django.views import View
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
import json


class SaveEmissionTransactionsView(View):

    @transaction.atomic
    def post(self, request):

        try:

            data = json.loads(request.body)

            company_id = data["company"]
            plant_id = data["plant"]
            fy_id = data["financial_year"]
            month_id = data["financial_month"]
            assignment_id = data.get("assignment")

            rows = data.get("rows", [])

            for row in rows:

                quantity = row.get("quantity", 0)

                if not quantity:
                    continue

                transaction_obj, created = (
                    EmissionTransaction.objects.update_or_create(

                        assignment_id=assignment_id,
                        activity_id=row["activity"],
                        source_id=row["source"],

                        defaults={
                            "company_id": company_id,
                            "plant_id": plant_id,
                            "financial_year_id": fy_id,
                            "financial_month_id": month_id,
                            "unit_id": row["unit"],
                            "quantity": quantity,
                            "remarks": row.get("remarks", ""),
                            "status": "DRAFT",
                            "created_by": request.user,
                        }

                    )
                )

                # Trigger calculation
                transaction_obj.save()

                if assignment_id:
                    EmissionAssignment.objects.filter(id=assignment_id,assignee=request.user,
                        status="ASSIGNED",).update(status="IN_PROGRESS")

            return JsonResponse({
                "success": True,
                "message": "Transactions saved successfully."
            })

        except Exception as e:

            return JsonResponse({
                "success": False,
                "message": str(e)
            })

from django.db.models import Sum

from django.db.models import Sum
from django.http import JsonResponse
from django.views import View

class LoadEmissionTransactionsView(View):

    def get(self, request):

        company = request.GET.get("company")
        plant = request.GET.get("plant")
        financial_year = request.GET.get("financial_year")
        financial_month = request.GET.get("financial_month")
        assignment_id = request.GET.get("assignment")

        data = []

        # ----------------------------------------------------
        # Assignment Mode
        # ----------------------------------------------------
        if assignment_id:

            transactions = (
                EmissionTransaction.objects
                .filter(assignment_id=assignment_id)
                .select_related("activity")
            )

            for transaction in transactions:

                data.append({

                    "activity": transaction.activity_id,

                    "source": transaction.source_id,

                    "quantity": str(transaction.quantity),

                    "factor": str(transaction.emission_factor),

                    "total": str(transaction.total_emission),

                    "status": transaction.status,

                })

        # ----------------------------------------------------
        # All Plants
        # ----------------------------------------------------
        elif plant == "ALL":

            transactions = (

                EmissionTransaction.objects

                .filter(
                    company_id=company,
                    financial_year_id=financial_year,
                    financial_month_id=financial_month,
                )

                .values(
                    "activity_id",
                    "source_id",
                    "emission_factor",
                    "status",
                )

                .annotate(
                    quantity=Sum("quantity"),
                    total_emission=Sum("total_emission"),
                )

            )

            for transaction in transactions:

                data.append({

                    "activity": transaction["activity_id"],

                    "source": transaction["source_id"],

                    "quantity": str(transaction["quantity"]),

                    "factor": str(transaction["emission_factor"]),

                    "total": str(transaction["total_emission"]),

                    "status": transaction["status"],

                })

        # ----------------------------------------------------
        # Single Plant
        # ----------------------------------------------------
        else:

            transactions = (

                EmissionTransaction.objects

                .filter(
                    company_id=company,
                    plant_id=plant,
                    financial_year_id=financial_year,
                    financial_month_id=financial_month,
                )

                .select_related("activity")

            )

            for transaction in transactions:

                data.append({

                    "activity": transaction.activity_id,

                    "source": transaction.source_id,

                    "quantity": str(transaction.quantity),

                    "factor": str(transaction.emission_factor),

                    "total": str(transaction.total_emission),

                    "status": transaction.status,

                })

        return JsonResponse({

            "success": True,

            "transactions": data,

        })


class ScopeCategoriesView(View):

    def get(self, request):

        scope_code = request.GET.get("scope")

        scope = (
            EmissionScope.objects
            .prefetch_related("categories")
            .filter(code=scope_code)
            .first()
        )

        if not scope:
            return JsonResponse({
                "success": False
            })

        categories = []

        for category in scope.categories.filter(
            is_active=True
        ).order_by("display_order"):

            categories.append({
                "id": category.id,
                "name": category.name,
            })

        return JsonResponse({
            "success": True,
            "scope": scope.name,
            "description": scope.description,
            "categories": categories,
        })
    


from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.models import User


class PlantUsersAPIView(APIView):

    def get(self, request):

        plant_id = request.GET.get("plant_id")

        if not plant_id:
            return Response({
                "success": False,
                "users": []
            })

        users = (
            User.objects
            .filter(
                assigned_plants__id=plant_id,
                is_active=True,
            )
            .distinct()
            .order_by("full_name", "username")
        )

        return Response({
            "success": True,
            "users": [
                {
                    "id": user.id,
                    "name": user.full_name or user.get_full_name() or user.username,
                    "employee_code": user.employee_code,
                    "designation": user.designation,
                    "department": user.department.name if user.department else "",
                }
                for user in users
            ]
        })

class EmissionAssignmentDashboardViewCompact(LoginRequiredMixin, TemplateView):
    login_url = "accounts:login"
    template_name = "emission/assignment.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get assignment_id from URL parameters
        assignment_id = self.request.GET.get('assignment')
        
        # Get all assignments
        assignments = (
            EmissionAssignment.objects
            .select_related(
                "company",
                "plant",
                "financial_year",
                "financial_month",
                "scope",
                "assignee",
                "assigner",
            )
            .prefetch_related(
                "transactions",
                "assignment_sources__source__activity",
            )
            .order_by('-created_at')
        )
        
        # Validate assignment_id
        highlight_assignment_id = None
        if assignment_id:
            try:
                assignments.get(id=assignment_id)
                highlight_assignment_id = assignment_id
            except EmissionAssignment.DoesNotExist:
                pass
        
        # ====== GET TIMESHEETS ======
        # Get timesheets for the current user
        timesheets = Timesheet.objects.filter(
            models.Q(user=self.request.user) | 
            models.Q(assignment__assignee=self.request.user)
        ).filter(
            models.Q(status='assigned') | models.Q(status='viewed')
        ).select_related('assignment', 'company', 'user').order_by('-created_at')[:10]
        
        timesheet_count = timesheets.count()
        
        # ====== GET NOTIFICATIONS ======
        # Get ALL notifications (read and unread) for the dropdown
        navbar_notifications = Notification.objects.filter(
            recipient=self.request.user
        ).exclude(
            title__icontains='Timesheet'
        ).order_by('-created_at')[:10]
        
        # ✅ Count ONLY unread notifications for the badge
        navbar_notification_count = Notification.objects.filter(
            recipient=self.request.user,
            is_read=False  # ✅ Only count unread
        ).exclude(
            title__icontains='Timesheet'
        ).count()
        
        # Get stats
        today = timezone.now().date()
        assignment_stats = {
            "assignment_count": assignments.count(),
            "open_count": assignments.filter(
                status__in=["ASSIGNED", "IN_PROGRESS", "SUBMITTED"]
            ).count(),
            "completed_count": assignments.filter(status="APPROVED").count(),
            "overdue_count": assignments.filter(
                due_date__lt=today
            ).exclude(status="APPROVED").count(),
        }
        
        
        # Update context
        context.update({
            "assignments": assignments,
            "assignment_scope": "ALL ASSIGNMENTS",
            "highlight_assignment_id": highlight_assignment_id,
            "timesheets": timesheets,
            "timesheet_count": timesheet_count,
            "navbar_notifications": navbar_notifications,  # All notifications (read + unread)
            "navbar_notification_count": navbar_notification_count,  # Only unread count
            **assignment_stats,
        })
        
        return context
class EmissionAssignmentDetailView(LoginRequiredMixin, TemplateView):

    template_name = "emission/assignment_detail.html"

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        assignment = get_object_or_404(
            EmissionAssignment.objects.select_related(
                "company",
                "plant",
                "financial_year",
                "financial_month",
                "scope",
                "assigner",
                "assignee",
            ),
            pk=self.kwargs["assignment_id"],
            assignee=self.request.user,
        )

        assigned_sources = (
            assignment.assignment_sources
            .select_related(
                "source",
                "source__activity",
                "source__activity__category",
            )
            .order_by(
                "source__activity__category__display_order",
                "source__activity__display_order",
                "source__display_order",
            )
        )

        transactions = (
            EmissionTransaction.objects
            .filter(assignment=assignment)
            .select_related(
                "activity",
                "source",
                "unit",
            )
        )

        context["assignment"] = assignment
        context["assigned_sources"] = assigned_sources
        context["transactions"] = transactions









from django.views import View
from django.http import JsonResponse
from django.db import transaction
import json


from django.views import View
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone
import json

from .models import (
    EmissionAssignment,
    EmissionTransaction,
)


class SubmitAssignmentView(View):

    @transaction.atomic
    def post(self, request):

        try:

            data = json.loads(request.body)

            assignment_id = data.get("assignment")

            if not assignment_id:
                return JsonResponse({
                    "success": False,
                    "message": "Assignment not found."
                })

            assignment = (
                EmissionAssignment.objects
                .filter(
                    id=assignment_id,
                    assignee=request.user,
                )
                .first()
            )

            if not assignment:
                return JsonResponse({
                    "success": False,
                    "message": "Invalid assignment."
                })

            # Prevent duplicate submission
            if assignment.status == "SUBMITTED":
                return JsonResponse({
                    "success": False,
                    "message": "Assignment has already been submitted."
                })

            # Load all transactions for this assignment
            transactions = EmissionTransaction.objects.filter(
                assignment=assignment
            )

            if not transactions.exists():
                return JsonResponse({
                    "success": False,
                    "message": "No emission data has been entered for this assignment."
                })

            # Update all transactions
            transactions.update(
                status="SUBMITTED",
                submitted_by=request.user,
                submitted_at=timezone.now(),
            )

            # Update assignment status
            assignment.status = "SUBMITTED"
            assignment.review_comments = ""

            assignment.save(
                update_fields=[
                    "status",
                    "review_comments",
                ]
            )

            return JsonResponse({
                "success": True,
                "message": "Assignment submitted successfully."
            })

        except Exception as e:

            return JsonResponse({
                "success": False,
                "message": str(e)
            })
        






