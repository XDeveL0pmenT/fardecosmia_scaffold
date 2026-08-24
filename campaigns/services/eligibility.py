"""Global trusted-GM eligibility policy.

Campaign roles remain on ``CampaignMembership``.  This module controls only
whether a real user has been trusted by a superuser to create campaigns and to
receive future GM memberships.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from accounts.services.verification import has_verified_transactional_email
from world.services.audit import record_audit


GM_ELIGIBILITY_CODENAME = "create_campaign_as_gm"
GM_ELIGIBILITY_PERMISSION = f"campaigns.{GM_ELIGIBILITY_CODENAME}"


def _direct_gm_permission(user):
    return user.user_permissions.filter(
        content_type__app_label="campaigns",
        codename=GM_ELIGIBILITY_CODENAME,
    )


def has_gm_eligibility(user):
    """Return trusted-GM eligibility; group permissions deliberately do not count.

    Eligibility is granted to an individual account by a superuser.  Ignoring
    group-derived permissions prevents a generic Group editor from becoming an
    alternate authority for this trust decision.
    """

    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and (user.is_superuser or _direct_gm_permission(user).exists())
    )


def gm_eligible_user_ids(user_ids):
    """Resolve eligibility for a collection without an ORM query per user."""

    return set(
        get_user_model()
        .objects.filter(pk__in=set(user_ids), is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(
                user_permissions__content_type__app_label="campaigns",
                user_permissions__codename=GM_ELIGIBILITY_CODENAME,
            )
        )
        .values_list("pk", flat=True)
        .distinct()
    )


def can_create_campaign(user):
    return bool(
        has_gm_eligibility(user)
        and has_verified_transactional_email(user)
    )


def require_gm_eligibility(user):
    if not has_gm_eligibility(user):
        raise PermissionDenied(
            "Создание кампаний доступно только доверенным Game Master. "
            "Обычный участник присоединяется по приглашению."
        )
    return user


def require_campaign_creation_access(user):
    require_gm_eligibility(user)
    if not has_verified_transactional_email(user):
        raise PermissionDenied("Для создания кампании подтвердите email.")
    return user


def _eligibility_permission():
    return Permission.objects.get(
        content_type__app_label="campaigns",
        codename=GM_ELIGIBILITY_CODENAME,
    )


def _user_label(user):
    return str(user.display_name or user.username)


@transaction.atomic
def set_gm_eligibility(*, actor, user_id, eligible):
    """Grant/revoke direct trusted-GM permission through the supported boundary."""

    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise PermissionDenied(
            "Только superuser может выдавать или отзывать право Game Master."
        )

    user_model = get_user_model()
    target = user_model.objects.select_for_update().get(pk=user_id)
    desired = bool(eligible)
    if target.is_superuser:
        if desired:
            return target
        raise ValidationError("Superuser всегда обладает правом Game Master.")

    permission = _eligibility_permission()
    before = _direct_gm_permission(target).exists()
    if before == desired:
        return target

    if desired:
        target.user_permissions.add(permission)
        action = "account.gm_eligibility_granted"
        summary = f"Пользователю {_user_label(target)} выдано право Game Master."
    else:
        target.user_permissions.remove(permission)
        action = "account.gm_eligibility_revoked"
        summary = f"У пользователя {_user_label(target)} отозвано право Game Master."

    record_audit(
        action=action,
        actor=actor,
        target=target,
        target_label=f"Пользователь {_user_label(target)}",
        summary=summary,
        before_state={
            "user_id": target.pk,
            "user_label": _user_label(target),
            "gm_eligible": before,
        },
        after_state={
            "user_id": target.pk,
            "user_label": _user_label(target),
            "gm_eligible": desired,
        },
    )
    return target
