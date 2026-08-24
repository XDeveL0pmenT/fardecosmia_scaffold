from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from campaigns.models import Campaign, CampaignMembership
from characters.models import Character
from integrations.roll20.models import Roll20CharacterBinding, Roll20Connection


class CharacterWorkspacePW1Tests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.gm = users.create_user(
            username="pw1-gm",
            password="pass",
            display_name="Мастер",
        )
        self.player = users.create_user(
            username="pw1-player",
            password="pass",
            display_name="Игрок",
        )
        self.other = users.create_user(
            username="pw1-other",
            password="pass",
            display_name="Другой игрок",
        )
        self.campaign = Campaign.objects.create(
            name="Грани Рассвета",
            description="История у далёкого моря.",
        )
        self.foreign_campaign = Campaign.objects.create(name="Чужая кампания")
        self.gm_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.gm,
            role=CampaignMembership.Role.GM,
        )
        self.player_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.player,
            role=CampaignMembership.Role.PLAYER,
        )
        self.other_membership = CampaignMembership.objects.create(
            campaign=self.campaign,
            user=self.other,
            role=CampaignMembership.Role.PLAYER,
        )
        self.foreign_membership = CampaignMembership.objects.create(
            campaign=self.foreign_campaign,
            user=self.other,
            role=CampaignMembership.Role.PLAYER,
        )

    def character(self, *, name="Аэрион", owner=None, campaign=None, **fields):
        return Character.objects.create(
            campaign=campaign or self.campaign,
            owner=owner,
            name=name,
            **fields,
        )

    def open_campaign(self, *, user=None, follow=False):
        self.client.force_login(user or self.player)
        return self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk]),
            follow=follow,
        )

    def test_player_campaign_card_has_no_requests_navigation(self):
        self.client.force_login(self.player)
        response = self.client.get(reverse("campaigns:list"))
        self.assertContains(response, "Открыть кампанию")
        self.assertNotContains(response, "Мои запросы")
        self.assertNotContains(
            response,
            reverse("world:my_approval_requests", args=[self.campaign.pk]),
        )

    def test_open_campaign_with_single_character_renders_workspace_directly(self):
        character = self.character(
            owner=self.player_membership,
            name="Лиора",
            biography="Слышит далёкие звёзды.",
        )
        response = self.open_campaign()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "characters/character_workspace.html")
        self.assertContains(response, "Лиора")
        self.assertContains(response, "Тиамана")
        self.assertContains(response, "Активные квесты")
        self.assertContains(response, "Быт / Обязательства")
        self.assertContains(response, "Команда")
        self.assertContains(response, "Заметки")
        self.assertContains(response, "Apotheosis")
        self.assertContains(response, "Инвентарь")
        self.assertNotContains(response, "Панель мастера")
        self.player_membership.refresh_from_db()
        self.assertIsNone(self.player_membership.active_character)
        self.assertEqual(response.context["active_character"], character)

    def test_no_character_is_human_empty_state_without_placeholder_row(self):
        before = Character.objects.count()
        response = self.open_campaign()
        self.assertContains(response, "Персонаж ещё не назначен")
        self.assertContains(response, "Вернуться ко всем кампаниям")
        self.assertEqual(Character.objects.count(), before)

    def test_multiple_characters_require_choice_and_switch_returns_to_workspace(self):
        first = self.character(name="Аэрион", owner=self.player_membership)
        second = self.character(name="Торвин", owner=self.player_membership)
        response = self.open_campaign()
        self.assertContains(response, "Выберите активного персонажа")
        self.assertContains(response, "Играть за Аэрион")
        self.assertContains(response, "Играть за Торвин")
        self.assertIsNone(response.context["active_character"])

        switch = self.client.post(
            reverse("characters:switch_active", args=[self.campaign.pk]),
            {"character": second.pk},
            follow=True,
        )
        self.assertRedirects(
            switch,
            reverse("campaigns:campaign_detail", args=[self.campaign.pk]),
        )
        self.assertTemplateUsed(switch, "characters/character_workspace.html")
        self.assertContains(switch, "Торвин")
        self.assertContains(switch, '<option value="{}" selected>'.format(second.pk))
        self.player_membership.refresh_from_db()
        self.assertEqual(self.player_membership.active_character, second)
        self.assertNotEqual(first, second)

    def test_player_surfaces_hide_old_knowledge_requests_and_roadmap_wording(self):
        self.character(owner=self.player_membership)
        response = self.open_campaign()
        for hidden_text in (
            "Мои запросы",
            "Что знает персонаж",
            "CharacterKnowledge",
            "ApprovalRequest",
            "normalized CharacterSheet",
            "Roll20 adapter",
            "после этапа",
            "появится после",
        ):
            with self.subTest(hidden_text=hidden_text):
                self.assertNotContains(response, hidden_text)

    def test_workspace_has_non_fake_hud_anchors_and_no_fake_gameplay_values(self):
        self.character(owner=self.player_membership)
        response = self.open_campaign()
        self.assertContains(response, "data-xp-hud-anchor", html=False)
        self.assertContains(response, "data-money-hud-anchor", html=False)
        self.assertNotContains(response, "0 XP")
        self.assertNotContains(response, "0 монет")
        self.assertNotContains(response, "0 золот")
        self.assertNotContains(response, "Зелье ×")
        self.assertNotContains(response, "Факел ×")

    def test_platform_navigation_and_account_settings_are_real_routes(self):
        self.character(owner=self.player_membership)
        response = self.open_campaign()
        self.assertContains(response, reverse("campaigns:list"))
        self.assertContains(response, reverse("accounts:settings"))
        self.assertContains(response, "Выйти")
        settings = self.client.get(reverse("accounts:settings"))
        self.assertEqual(settings.status_code, 200)
        self.assertContains(settings, "Настройки аккаунта")
        self.assertContains(settings, "Игрок")

    def test_gm_only_and_raw_roll20_data_are_absent_from_player_workspace(self):
        character = self.character(
            owner=self.player_membership,
            biography="Безопасная биография",
            gm_notes="gm-only-secret",
            public_notes="legacy-public-placeholder",
        )
        roll20 = Roll20Connection.objects.create(campaign=self.campaign)
        Roll20CharacterBinding.objects.create(
            connection=roll20,
            character=character,
            roll20_character_id="raw-roll20-secret-id",
            raw_attributes={"secret": "raw-payload-secret"},
        )
        response = self.open_campaign()
        self.assertContains(response, "Безопасная биография")
        for secret in (
            "gm-only-secret",
            "legacy-public-placeholder",
            "raw-roll20-secret-id",
            "raw-payload-secret",
        ):
            self.assertNotContains(response, secret)

    def test_idor_foreign_campaign_and_character_selection_are_denied(self):
        own = self.character(owner=self.player_membership)
        other = self.character(name="Чужой", owner=self.other_membership)
        foreign = self.character(
            name="Дальний",
            owner=self.foreign_membership,
            campaign=self.foreign_campaign,
        )
        self.client.force_login(self.player)
        self.assertEqual(
            self.client.get(
                reverse("campaigns:campaign_detail", args=[self.foreign_campaign.pk])
            ).status_code,
            403,
        )
        switch_url = reverse("characters:switch_active", args=[self.campaign.pk])
        self.assertEqual(self.client.post(switch_url, {"character": other.pk}).status_code, 403)
        self.assertEqual(self.client.post(switch_url, {"character": foreign.pk}).status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("characters:detail", args=[self.campaign.pk, other.pk])
            ).status_code,
            404,
        )
        self.assertTrue(own.is_active)

    def test_archived_or_unowned_character_cannot_become_active(self):
        archived = self.character(
            name="Архивный",
            owner=self.player_membership,
            is_active=False,
        )
        unowned = self.character(name="Свободный")
        self.client.force_login(self.player)
        url = reverse("characters:switch_active", args=[self.campaign.pk])
        self.assertEqual(self.client.post(url, {"character": archived.pk}).status_code, 403)
        self.assertEqual(self.client.post(url, {"character": unowned.pk}).status_code, 403)
        self.player_membership.refresh_from_db()
        self.assertIsNone(self.player_membership.active_character)

    def test_legacy_player_detail_is_not_primary_destination(self):
        character = self.character(owner=self.player_membership)
        self.client.force_login(self.player)
        response = self.client.get(
            reverse("characters:detail", args=[self.campaign.pk, character.pk])
        )
        self.assertRedirects(
            response,
            reverse("campaigns:campaign_detail", args=[self.campaign.pk]),
        )

    def test_gm_landing_and_approval_queue_remain_separate_and_available(self):
        response = self.open_campaign(user=self.gm)
        self.assertTemplateUsed(response, "campaigns/campaign_detail.html")
        self.assertContains(response, "Панель мастера")
        self.assertNotContains(response, "Тиамана")
        queue = self.client.get(
            reverse("world:campaign_approval_queue", args=[self.campaign.pk])
        )
        self.assertEqual(queue.status_code, 200)
        self.assertContains(queue, "Запросы на одобрение")

    def test_compatibility_requester_route_remains_but_is_not_discoverable(self):
        self.client.force_login(self.player)
        route = reverse("world:my_approval_requests", args=[self.campaign.pk])
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200)
        campaign_list = self.client.get(reverse("campaigns:list"))
        workspace = self.client.get(
            reverse("campaigns:campaign_detail", args=[self.campaign.pk])
        )
        self.assertNotContains(campaign_list, route)
        self.assertNotContains(workspace, route)

    def test_workspace_queries_remain_bounded_with_many_controlled_characters(self):
        selected = None
        for index in range(20):
            character = self.character(
                owner=self.player_membership,
                name=f"Герой {index:02d}",
            )
            selected = selected or character
        self.player_membership.active_character = selected
        self.player_membership.save(update_fields=["active_character"])
        self.client.force_login(self.player)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("campaigns:campaign_detail", args=[self.campaign.pk])
            )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 12)

