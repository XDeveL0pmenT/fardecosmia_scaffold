from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Пользователь Фардекосмии.

    Не хранит роль "игрок/мастер" глобально: роль определяется отдельно
    через CampaignMembership, потому что один и тот же человек может быть
    мастером одной кампании и игроком другой.
    """

    display_name = models.CharField(
        "Отображаемое имя",
        max_length=120,
        blank=True,
    )
    avatar = models.ImageField(
        "Аватар",
        upload_to="users/avatars/",
        blank=True,
        null=True,
    )

    def __str__(self):
        return self.display_name or self.username
