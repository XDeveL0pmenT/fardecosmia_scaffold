from dataclasses import dataclass
from datetime import timedelta
import secrets
import uuid

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from accounts.services.email_addresses import mask_email_address, normalize_email_address
from campaigns.models import Campaign, CampaignInvitation, CampaignMembership
from world.services.access import require_campaign_gm
from world.services.audit import record_audit


class InvitationError(Exception):
    pass


class InvitationNotFound(InvitationError):
    pass


class InvitationUnavailable(InvitationError):
    pass


class InvitationEmailMismatch(InvitationError):
    pass


@dataclass(frozen=True)
class InvitationCreationResult:
    invitation: CampaignInvitation
    token: str
    replaced_existing: bool


@dataclass(frozen=True)
class InvitationAcceptanceResult:
    invitation: CampaignInvitation
    membership: CampaignMembership
    already_member: bool


def _user_label(user):
    return str(user.display_name or user.username)


def _serialize_invitation(invitation):
    return {
        "email_masked": mask_email_address(invitation.email_normalized),
        "role": invitation.role,
        "expires_at": invitation.expires_at.isoformat(),
        "status": invitation.status_label,
        "created_by": invitation.created_by_label_snapshot,
    }


def _generate_token():
    return secrets.token_urlsafe(32)


def resolve_invitation_token(token, *, for_update=False):
    token = str(token or "").strip()
    if len(token) < 32:
        raise InvitationNotFound("Приглашение не найдено.")
    queryset = CampaignInvitation.objects.select_related("campaign", "created_by")
    if for_update:
        queryset = queryset.select_for_update()
    invitation = queryset.filter(token_prefix=token[:16]).first()
    if invitation is None or not check_password(token, invitation.token_hash):
        raise InvitationNotFound("Приглашение не найдено.")
    return invitation


@transaction.atomic
def create_campaign_invitation(*, campaign, actor, email):
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    require_campaign_gm(actor, locked_campaign)
    email = normalize_email_address(email)
    validate_email(email)
    if CampaignMembership.objects.filter(
        campaign=locked_campaign,
        user__email__iexact=email,
    ).exists():
        raise InvitationUnavailable("Пользователь с таким email уже состоит в кампании.")

    operation_id = uuid.uuid4()
    now = timezone.now()
    existing = (
        CampaignInvitation.objects.select_for_update()
        .filter(
            campaign=locked_campaign,
            email_normalized=email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        .first()
    )
    replaced = existing is not None
    if existing is not None:
        before = _serialize_invitation(existing)
        existing.revoked_at = now
        existing.revoked_by = actor
        existing.revoked_by_label_snapshot = _user_label(actor)
        existing.save(
            update_fields=[
                "revoked_at",
                "revoked_by",
                "revoked_by_label_snapshot",
            ]
        )
        record_audit(
            action="campaign_invitation.revoked",
            actor=actor,
            campaign=locked_campaign,
            target=existing,
            summary=(
                f"Предыдущее приглашение для {mask_email_address(email)} отозвано "
                "при выпуске нового."
            ),
            before_state=before,
            after_state=_serialize_invitation(existing),
            operation_id=operation_id,
        )

    token = _generate_token()
    invitation = CampaignInvitation.objects.create(
        campaign=locked_campaign,
        email_normalized=email,
        role=CampaignMembership.Role.PLAYER,
        created_by=actor,
        created_by_label_snapshot=_user_label(actor),
        expires_at=now
        + timedelta(seconds=settings.CAMPAIGN_INVITATION_LIFETIME_SECONDS),
        token_prefix=token[:16],
        token_hash=make_password(token),
    )
    record_audit(
        action="campaign_invitation.created",
        actor=actor,
        campaign=locked_campaign,
        target=invitation,
        summary=f"Создано приглашение игроку {mask_email_address(email)}.",
        before_state=None,
        after_state=_serialize_invitation(invitation),
        metadata={"replaced_existing": replaced},
        operation_id=operation_id,
    )
    return InvitationCreationResult(
        invitation=invitation,
        token=token,
        replaced_existing=replaced,
    )


def record_invitation_delivery(*, invitation, sent):
    now = timezone.now()
    field = "sent_at" if sent else "delivery_failed_at"
    CampaignInvitation.objects.filter(pk=invitation.pk).update(**{field: now})
    setattr(invitation, field, now)
    return invitation


@transaction.atomic
def revoke_campaign_invitation(*, campaign, invitation_id, actor):
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    require_campaign_gm(actor, locked_campaign)
    try:
        invitation = CampaignInvitation.objects.select_for_update().get(
            pk=invitation_id,
            campaign=locked_campaign,
        )
    except CampaignInvitation.DoesNotExist as error:
        raise InvitationNotFound("Приглашение не найдено.") from error
    if invitation.accepted_at is not None:
        raise InvitationUnavailable("Принятое приглашение уже нельзя отозвать.")
    if invitation.revoked_at is not None:
        raise InvitationUnavailable("Приглашение уже отозвано.")
    before = _serialize_invitation(invitation)
    invitation.revoked_at = timezone.now()
    invitation.revoked_by = actor
    invitation.revoked_by_label_snapshot = _user_label(actor)
    invitation.save(
        update_fields=["revoked_at", "revoked_by", "revoked_by_label_snapshot"]
    )
    record_audit(
        action="campaign_invitation.revoked",
        actor=actor,
        campaign=locked_campaign,
        target=invitation,
        summary=(
            f"Приглашение для {mask_email_address(invitation.email_normalized)} отозвано."
        ),
        before_state=before,
        after_state=_serialize_invitation(invitation),
    )
    return invitation


def _accept_locked_invitation(*, invitation, actor):
    locked_campaign = Campaign.objects.select_for_update().get(pk=invitation.campaign_id)
    now = timezone.now()
    if invitation.accepted_at is not None:
        raise InvitationUnavailable("Это приглашение уже использовано.")
    if invitation.revoked_at is not None:
        raise InvitationUnavailable("Это приглашение отозвано Game Master.")
    if invitation.expires_at <= now:
        raise InvitationUnavailable(
            "Это приглашение больше не действует. Попросите Game Master отправить новое."
        )
    if not actor.is_authenticated or not actor.has_verified_email:
        raise PermissionDenied("Для вступления подтвердите email.")
    actor_email = normalize_email_address(actor.email)
    if actor_email != invitation.email_normalized:
        raise InvitationEmailMismatch(
            "Приглашение отправлено на другой email. Войдите в подходящий подтверждённый аккаунт."
        )

    membership = CampaignMembership.objects.filter(
        campaign=locked_campaign,
        user=actor,
    ).first()
    already_member = membership is not None
    if membership is None:
        membership = CampaignMembership.objects.create(
            campaign=locked_campaign,
            user=actor,
            role=CampaignMembership.Role.PLAYER,
        )
    invitation.accepted_at = now
    invitation.accepted_by = actor
    invitation.accepted_by_label_snapshot = _user_label(actor)
    invitation.save(
        update_fields=[
            "accepted_at",
            "accepted_by",
            "accepted_by_label_snapshot",
        ]
    )
    if already_member:
        record_audit(
            action="campaign_invitation.accepted",
            actor=actor,
            campaign=locked_campaign,
            target=invitation,
            summary=(
                f"{_user_label(actor)} подтвердил приглашение, уже состоя в кампании."
            ),
            before_state={"status": "Ожидает"},
            after_state=_serialize_invitation(invitation),
        )
    else:
        record_audit(
            action="campaign_member.joined",
            actor=actor,
            campaign=locked_campaign,
            target=membership,
            summary=f"Игрок {_user_label(actor)} присоединился к кампании.",
            before_state=None,
            after_state={
                "user_label": _user_label(actor),
                "role": CampaignMembership.Role.PLAYER,
                "invitation_email_masked": mask_email_address(
                    invitation.email_normalized
                ),
            },
        )
    return InvitationAcceptanceResult(
        invitation=invitation,
        membership=membership,
        already_member=already_member,
    )


@transaction.atomic
def accept_campaign_invitation(*, token, actor):
    invitation = resolve_invitation_token(token, for_update=True)
    return _accept_locked_invitation(invitation=invitation, actor=actor)


@transaction.atomic
def accept_campaign_invitation_by_id(*, invitation_id, actor):
    try:
        invitation = (
            CampaignInvitation.objects.select_for_update()
            .select_related("campaign")
            .get(pk=invitation_id)
        )
    except CampaignInvitation.DoesNotExist as error:
        raise InvitationNotFound("Приглашение не найдено.") from error
    return _accept_locked_invitation(invitation=invitation, actor=actor)
