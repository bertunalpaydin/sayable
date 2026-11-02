from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("profile/", views.profile_session, name="profile_session"),
    path("scripts/", views.script_list, name="script_list"),
    path("scripts/new/", views.script_new, name="script_new"),
    path("scripts/<int:pk>/", views.script_edit, name="script_edit"),
    path("scripts/<int:pk>/delete/", views.script_delete, name="script_delete"),
    path("scripts/<int:pk>/rehearse/", views.rehearse, name="rehearse"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/delete-practice/", views.delete_practice, name="delete_practice"),
    path("signup/", views.signup, name="signup"),
    path("api/record/", views.api_record, name="api_record"),
    path("api/check/", views.api_check, name="api_check"),
    path("api/suggest/", views.api_suggest, name="api_suggest"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
]
