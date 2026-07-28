from django.urls import path
from .views_excel import download_scope_template, upload_scope_template
from .api_views import ApproveAssignmentView, RejectAssignmentView
from .views import (
    EmissionAssignmentDashboardView,
    EmissionsDashboardView, 
    EmissionsDashboardDataView,
    PlantUsersAPIView,
    SaveEmissionAssignmentAPIView,
    ScopeDashboardView,
    ESGDisclosureView,
    CategoryActivitiesView,
    ActivityFactorView,
    SaveEmissionTransactionsView,
    LoadEmissionTransactionsView,
    ScopeCategoriesView,
    EmissionAssignmentDetailView,
    SubmitAssignmentView,
    CheckAssignedSourcesAPIView,
)

app_name = "emission"

urlpatterns = [
    # ===== Analytical DASHBOARD =====
    path("", EmissionsDashboardView.as_view(), name="dashboard"),
    path("api/data/", EmissionsDashboardDataView.as_view(), name="dashboard-data"),

    #====== SCOPE =======
    path("scope_dataentry/", ScopeDashboardView.as_view(), name="scope_dataentry"),
    path("api/category-activities/",CategoryActivitiesView.as_view(),name="category-activities"),
    path("api/activity-factor/",ActivityFactorView.as_view(),name="activity-factor"),
    path("api/save-transactions/",SaveEmissionTransactionsView.as_view(),name="save-transactions"),
    path("api/load-transactions/",LoadEmissionTransactionsView.as_view(),name="load-transactions"),
    path("api/scope-categories/",ScopeCategoriesView.as_view(),name="scope_categories"),
    path("api/plant-users/",PlantUsersAPIView.as_view(),name="plant_users"),
    
    
    #=====report====
    path("esg/", ESGDisclosureView.as_view(), name="esg-disclosure"),

    #====== Correct Working Use ASSIGNMENT=====
    path("assignments/",EmissionAssignmentDashboardView.as_view(),name="assignment_dashboard"),
    path("api/assignment/save/",SaveEmissionAssignmentAPIView.as_view(),name="save-emission-assignment"),
    path("api/submit-assignment/",SubmitAssignmentView.as_view(),name="submit_assignment"),
    path("assignments/<int:assignment_id>/",EmissionAssignmentDetailView.as_view(),name="assignment_detail"),
    path("api/approve-assignment/",ApproveAssignmentView.as_view(),name="approve_assignment"),
    path("api/reject-assignment/",RejectAssignmentView.as_view(),name="reject_assignment"),
    path("api/scope-template/download/", download_scope_template,name="download_scope_template"),
    path("api/scope-template/upload/", upload_scope_template,name="upload_scope_template"),
    path("api/assignment/check-assigned-sources/",CheckAssignedSourcesAPIView.as_view(),name="check_assigned_sources"),
]
