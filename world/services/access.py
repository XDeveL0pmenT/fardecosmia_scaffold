from django.core.exceptions import PermissionDenied

from campaigns.models import CampaignMembership


GLOBAL_CANON_PERMISSION = "world.manage_global_canon"


def can_manage_global_canon(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.has_perm(GLOBAL_CANON_PERMISSION))
    )


def can_view_global_atlas(user):
    if not user or not user.is_authenticated:
        return False
    if can_manage_global_canon(user):
        return True
    return user.campaign_memberships.filter(
        role=CampaignMembership.Role.GM,
    ).exists()


def can_view_campaign(user, campaign):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or campaign.memberships.filter(user=user).exists()


def can_manage_campaign(user, campaign):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or campaign.memberships.filter(
        user=user,
        role=CampaignMembership.Role.GM,
    ).exists()


def require_global_canon_editor(user):
    if not can_manage_global_canon(user):
        raise PermissionDenied("Требуется право редактора глобального канона.")
    return user


def require_global_atlas_viewer(user):
    if not can_view_global_atlas(user):
        raise PermissionDenied(
            "Объективный атлас доступен мастерам кампаний и редакторам канона."
        )
    return user


def require_campaign_member(user, campaign):
    if user.is_superuser:
        return None
    membership = campaign.memberships.filter(user=user).first()
    if membership is None:
        raise PermissionDenied("Нет доступа к этой кампании.")
    return membership


def require_campaign_gm(user, campaign):
    if user.is_superuser:
        return None
    membership = campaign.memberships.filter(user=user).first()
    if membership is None or membership.role != CampaignMembership.Role.GM:
        raise PermissionDenied("Доступ только для мастера этой кампании.")
    return membership
