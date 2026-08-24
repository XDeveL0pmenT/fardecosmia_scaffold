from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from accounts.forms import RegistrationForm, VerificationCodeForm
from accounts.services.registration import RegistrationConflict, register_account
from accounts.services.verification import (
    VerificationAttemptsExhausted,
    VerificationCodeExpired,
    VerificationCodeInvalid,
    VerificationCooldown,
    issue_verification_challenge,
    verification_page_context,
    verify_email_code,
)


def _safe_next(request, value):
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ""


def _after_verification_url(request):
    invite_id = request.session.get("pending_campaign_invite_id")
    if invite_id:
        return reverse("campaigns:invitation_resume")
    next_url = _safe_next(request, request.session.pop("onboarding_next", ""))
    return next_url or reverse("campaigns:list")


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        if request.user.has_verified_email or not request.user.email_verification_required:
            return redirect("campaigns:list")
        return redirect("accounts:verify_email")

    next_url = _safe_next(request, request.GET.get("next", ""))
    if next_url and not next_url.startswith("/invite/"):
        request.session["onboarding_next"] = next_url
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            result = register_account(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password1"],
            )
        except RegistrationConflict as error:
            form.add_error(None, str(error))
        else:
            login(request, result.user)
            if result.email_sent:
                messages.success(
                    request,
                    "Аккаунт создан. Код подтверждения отправлен на ваш email.",
                )
            else:
                messages.warning(
                    request,
                    "Аккаунт создан, но письмо сейчас не удалось отправить. "
                    "Попробуйте отправить код повторно.",
                )
            return redirect("accounts:verify_email")
    return render(request, "registration/register.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def verify_email_view(request):
    if request.user.has_verified_email:
        return redirect(_after_verification_url(request))
    form = VerificationCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            verify_email_code(user=request.user, code=form.cleaned_data["code"])
        except (
            VerificationCodeInvalid,
            VerificationCodeExpired,
            VerificationAttemptsExhausted,
        ) as error:
            form.add_error("code", str(error))
        else:
            messages.success(request, "Email подтверждён. Добро пожаловать!")
            return redirect(_after_verification_url(request))
    context = verification_page_context(request.user)
    context["form"] = form
    return render(request, "registration/verify_email.html", context)


@login_required
@require_POST
def resend_verification_view(request):
    if request.user.has_verified_email:
        messages.info(request, "Этот email уже подтверждён.")
        return redirect("accounts:verify_email")
    try:
        result = issue_verification_challenge(user=request.user)
    except VerificationCooldown as error:
        messages.warning(request, str(error))
    except Exception as error:
        # Validation errors are safe/human messages; delivery internals are
        # already logged by the centralized email service.
        message = getattr(error, "message", None) or str(error)
        messages.error(request, message or "Не удалось подготовить новый код.")
    else:
        if result.email_sent:
            messages.success(request, "Новый код отправлен. Старый код больше не действует.")
        else:
            messages.warning(
                request,
                "Письмо сейчас не удалось отправить. Попробуйте ещё раз чуть позже.",
            )
    return redirect("accounts:verify_email")


@login_required
def account_settings_view(request):
    """Small platform-level account landing for the PW1 shell."""

    return render(request, "accounts/account_settings.html")
