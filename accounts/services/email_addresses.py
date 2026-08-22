"""Canonical email handling shared by registration, verification and invites."""


def normalize_email_address(value):
    """Return the project's case-insensitive canonical email representation."""

    if value is None:
        return ""
    return str(value).strip().casefold()


def mask_email_address(value):
    email = normalize_email_address(value)
    if "@" not in email:
        return "адрес скрыт"
    local, domain = email.rsplit("@", 1)
    if not local:
        return f"***@{domain}"
    visible = local[0]
    return f"{visible}***@{domain}"
