from django.apps import AppConfig


class Roll20Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.roll20"
    label = "roll20"
    verbose_name = "Roll20 Integration"
