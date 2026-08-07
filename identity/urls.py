from django.urls import path

from . import views

app_name = "identity"

urlpatterns = [
    path("", views.home, name="home"),
    path("status/", views.status, name="status"),
    path("status/poll/", views.status_poll, name="status_poll"),
    path("leave/", views.leave, name="leave"),
    path("staff/approvals/", views.staff_approvals, name="staff_approvals"),
    path("staff/approvals/<int:member_id>/approve/", views.staff_approve, name="staff_approve"),
    path("staff/approvals/<int:member_id>/reject/", views.staff_reject, name="staff_reject"),
    path("staff/approvals/<int:member_id>/remove/", views.staff_remove_member, name="staff_remove_member"),
]
