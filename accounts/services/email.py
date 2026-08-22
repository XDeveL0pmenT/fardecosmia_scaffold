"""Central transactional-email boundary.

Provider-specific SMTP details live in Django settings/environment variables.
This module deliberately logs no template context because it may contain a
verification code or a password-reset/invitation token.
"""

from dataclasses import dataclass
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from accounts.services.email_addresses import mask_email_address


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailDeliveryResult:
    sent: bool


def send_templated_email(
    *,
    to_email,
    subject_template,
    text_template,
    html_template=None,
    context=None,
):
    context = {} if context is None else dict(context)
    subject = " ".join(render_to_string(subject_template, context).splitlines()).strip()
    text_body = render_to_string(text_template, context)
    html_body = render_to_string(html_template, context) if html_template else None
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    try:
        sent_count = message.send(fail_silently=False)
    except Exception as error:
        # Provider exception strings are deliberately omitted: SMTP libraries
        # may include endpoint details or credentials in them.  The exception
        # class is enough for operations while recipients remain masked.
        logger.error(
            "Transactional email delivery failed: template=%s recipient=%s error_type=%s",
            subject_template,
            mask_email_address(to_email),
            type(error).__name__,
        )
        return EmailDeliveryResult(sent=False)
    return EmailDeliveryResult(sent=sent_count == 1)


def send_verification_email(*, user, code):
    return send_templated_email(
        to_email=user.email,
        subject_template="emails/verify_email_subject.txt",
        text_template="emails/verify_email.txt",
        html_template="emails/verify_email.html",
        context={
            "user": user,
            "code": code,
            "lifetime_minutes": settings.EMAIL_VERIFICATION_LIFETIME_SECONDS // 60,
        },
    )


def send_campaign_invitation_email(*, invitation, invite_url):
    return send_templated_email(
        to_email=invitation.email_normalized,
        subject_template="emails/campaign_invitation_subject.txt",
        text_template="emails/campaign_invitation.txt",
        html_template="emails/campaign_invitation.html",
        context={
            "invitation": invitation,
            "campaign": invitation.campaign,
            "inviter_label": invitation.created_by_label_snapshot,
            "invite_url": invite_url,
        },
    )
