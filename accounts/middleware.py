from django.shortcuts import redirect

from accounts.services.verification import verification_required_for_access


class VerifiedEmailRequiredMiddleware:
    """Restrict newly registered, unverified users to onboarding-safe routes."""

    allowed_view_names = {
        "accounts:register",
        "accounts:verify_email",
        "accounts:resend_verification",
        "login",
        "logout",
        "password_reset",
        "password_reset_done",
        "password_reset_confirm",
        "password_reset_complete",
        "campaigns:invitation_detail",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not verification_required_for_access(request.user):
            return None
        match = request.resolver_match
        if match is not None and match.view_name in self.allowed_view_names:
            return None
        request.session.setdefault("onboarding_next", request.get_full_path())
        return redirect("accounts:verify_email")
