from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from crm import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="crm/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("healthz/", views.healthz, name="healthz"),
    path("", views.board, name="home"),
    path("board/", views.board, name="board"),
    path("leads/", views.inbox, name="inbox"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("channels/", views.channels, name="channels"),
    path("doc", views.project_doc, name="project_doc"),
    path("doc/", views.project_doc, name="project_doc_slash"),
    path("leads/new/", views.lead_new, name="lead_new"),
    path("leads/<int:lead_id>/", views.lead_detail, name="lead_detail"),
    path("leads/<int:lead_id>/edit/", views.lead_edit, name="lead_edit"),
    path("leads/<int:lead_id>/status/", views.lead_status, name="lead_status"),
    path("leads/<int:lead_id>/amount/", views.lead_amount, name="lead_amount"),
    path("leads/<int:lead_id>/next-contact/", views.lead_next_contact, name="lead_next_contact"),
    path("leads/<int:lead_id>/tags/", views.lead_add_tag, name="lead_add_tag"),
    path("leads/<int:lead_id>/tags/<int:tag_id>/remove/", views.lead_remove_tag, name="lead_remove_tag"),
    path("guide/", views.guide, name="guide"),
]
