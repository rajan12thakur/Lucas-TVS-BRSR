from django.urls import path

from .api_views import *
from .views import *


app_name = "brsr"

urlpatterns = [
    path("", brsr_list, name="brsr_list"),
    path("brsr-list/", brsr_list, name="brsr_list_legacy"),
    path("workspace/", brsr_workspace, name="question_workspace"),
    path("workspace/<slug:section_code>/", brsr_workspace, name="question_workspace_section"),
    path("workspace/<slug:section_code>/<slug:principle_slug>/", brsr_workspace, name="question_workspace_principle",),
    path("workspace/<slug:section_code>/<slug:principle_slug>/<str:question_id>/", brsr_workspace, name="question_workspace_question",),
    path("assignments/", AssignmentDashboardView.as_view(), name="assignment_dashboard"),
    path("approvals/", ApprovalDashboardView.as_view(), name="approval_dashboard"),
    path('assignment/<int:assignment_id>/',  AssignmentDetailView.as_view(), name='assignment_detail'),
    path("assignment/<int:assignment_id>/review-comments/", AssignmentReviewCommentView.as_view(), name="assignment_review_comments"),
    path("api/workspace/", BRSRWorkspaceDataAPIView.as_view(), name="workspace_api"),
    path("api/assignment-options/", AssignmentOptionsAPIView.as_view(), name="assignment_options_api"),
    path("api/questions/<str:question_id>/", QuestionDetailAPIView.as_view(), name="question_detail_api"),
    path("api/questions/<str:question_id>/save/", QuestionSaveAPIView.as_view(), name="question_save_api"),
    path("api/questions/<str:question_id>/submit/", QuestionSubmitAPIView.as_view(), name="question_submit_api",),
    path("api/questions/<str:question_id>/approve/", QuestionApproveAPIView.as_view(), name="question_approve_api",),
    path("api/questions/<str:question_id>/reject/", QuestionRejectAPIView.as_view(), name="question_reject_api",),
    path("api/questions/<str:question_id>/comment/", QuestionReviewCommentAPIView.as_view(), name="question_comment_api",),
    path("api/assignments/<int:assignment_id>/approve/", AssignmentApproveAPIView.as_view(), name="assignment_approve_api"),
    path("api/assignments/<int:assignment_id>/reject/", AssignmentRejectAPIView.as_view(), name="assignment_reject_api"),
    path("api/assignments/", AssignmentCreateAPIView.as_view(), name="assignment_create_api"),
    path("api/assignment-schedules/", AssignmentScheduleCreateAPIView.as_view(), name="assignment_schedule_create_api",),
    path("api/assignment-schedules/list/", AssignmentScheduleListAPIView.as_view(), name="assignment_schedule_list_api",),
    path("api/assignment-schedules/<int:schedule_id>/toggle/", AssignmentScheduleToggleAPIView.as_view(), name="assignment_schedule_toggle_api",),
]
