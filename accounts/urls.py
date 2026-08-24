from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from accounts.forms import FardecosmiaPasswordResetForm
from accounts import views


app_name = "accounts"

urlpatterns = [
    path("settings/", views.account_settings_view, name="settings"),
    path("register/", views.register_view, name="register"),
    path("verify-email/", views.verify_email_view, name="verify_email"),
    path(
        "verify-email/resend/",
        views.resend_verification_view,
        name="resend_verification",
    ),
]


password_reset_patterns = [
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=FardecosmiaPasswordResetForm,
            template_name="registration/password_reset_form.html",
            email_template_name="emails/password_reset.txt",
            html_email_template_name="emails/password_reset.html",
            subject_template_name="emails/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
