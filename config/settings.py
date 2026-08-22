import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-only-change-me"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "accounts.apps.AccountsConfig",
    "campaigns",
    "characters",
    "world",
    "integrations.roll20.apps.Roll20Config",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.VerifiedEmailRequiredMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "campaigns.context_processors.campaign_permissions",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # Local development may have the Django server, PyCharm's database
            # viewer and management commands reading SQLite concurrently. WAL
            # permits readers during a write; IMMEDIATE obtains the write lock
            # at the start of advance_world() instead of failing mid-transaction.
            "timeout": 30,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Dublin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Development prints transactional messages to the terminal. Production can
# select SMTP entirely through environment variables without storing secrets in
# Git or the database.
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("DJANGO_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = _env_bool("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("DJANGO_EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv(
    "DJANGO_DEFAULT_FROM_EMAIL",
    "Фардекосмия <noreply@localhost>",
)

EMAIL_VERIFICATION_LIFETIME_SECONDS = int(
    os.getenv("FARDECOSMIA_EMAIL_CODE_LIFETIME_SECONDS", "600")
)
EMAIL_VERIFICATION_MAX_ATTEMPTS = int(
    os.getenv("FARDECOSMIA_EMAIL_CODE_MAX_ATTEMPTS", "5")
)
EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS = int(
    os.getenv("FARDECOSMIA_EMAIL_CODE_RESEND_COOLDOWN_SECONDS", "60")
)
CAMPAIGN_INVITATION_LIFETIME_SECONDS = int(
    os.getenv("FARDECOSMIA_INVITE_LIFETIME_SECONDS", str(7 * 24 * 60 * 60))
)
PASSWORD_RESET_TIMEOUT = int(
    os.getenv("FARDECOSMIA_PASSWORD_RESET_TIMEOUT_SECONDS", "3600")
)
