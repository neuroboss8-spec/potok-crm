import uuid
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import IntakeSession, Lead, Tag, UpdateReceipt
from .services import add_lead_tag, complete_intake, contact_is_valid, create_lead, get_or_create_tag, normalize_tag, remove_lead_tag


class LeadServiceTests(TestCase):
    def setUp(self):
        self.data = {
            "name": "Анна Примерова",
            "contact_type": "email",
            "contact_value": "anna@example.com",
            "request": "Нужен небольшой сайт.",
        }

    def test_submission_token_is_idempotent(self):
        token = uuid.uuid4()
        first, first_created = create_lead(data=self.data, submission_id=token)
        second, second_created = create_lead(data=self.data, submission_id=token)
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Lead.objects.count(), 1)

    def test_tag_name_uses_unicode_compatibility_and_casefold(self):
        first = add_lead_tag(lead=create_lead(data=self.data)[0], value="  ＃ САЙТ   ")[0]
        second, created = get_or_create_tag("сайт")
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Tag.objects.count(), 1)
        self.assertEqual(normalize_tag("#Сайт")[1], "сайт")

    def test_tag_can_be_removed_from_only_its_lead(self):
        lead = create_lead(data=self.data)[0]
        tag = add_lead_tag(lead=lead, value="проверка")[0]
        remove_lead_tag(lead=lead, tag_id=tag.pk)
        self.assertFalse(lead.tags.exists())

    def test_contact_type_validation_does_not_guess_country_code(self):
        self.assertTrue(contact_is_valid("phone", "+7 999 123-45-67"))
        self.assertFalse(contact_is_valid("phone", "8 999 123-45-67"))
        self.assertTrue(contact_is_valid("email", "person@example.com"))
        self.assertFalse(contact_is_valid("email", "not-an-email"))


class IntakeTransactionTests(TestCase):
    def test_repeated_confirmation_with_different_callback_ids_reuses_lead(self):
        session = IntakeSession.objects.create(
            bot_id=9001,
            chat_id=8001,
            user_id=7001,
            step=IntakeSession.Step.REVIEW,
            validated_data={
                "name": "Тестовая заявка",
                "contact_type": "email",
                "contact_value": "demo@example.com",
                "request": "Проверка повторной отправки.",
            },
        )
        first, created_first = complete_intake(session_id=session.pk, update_id="callback-a")
        second, created_second = complete_intake(session_id=session.pk, update_id="callback-b")
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(UpdateReceipt.objects.count(), 2)


class InboxViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="reviewer", password="long-enough-demo-password")
        self.client.force_login(user)
        self.first = create_lead(data={
            "name": "Анна Сайтова",
            "contact_type": "email",
            "contact_value": "anna@example.com",
            "request": "Хочу обновить сайт.",
        })[0]
        self.second = create_lead(data={
            "name": "Борис Рекламов",
            "contact_type": "email",
            "contact_value": "boris@example.com",
            "request": "Нужна реклама.",
        })[0]
        self.tag = add_lead_tag(lead=self.first, value="Сайт")[0]
        add_lead_tag(lead=self.second, value="Реклама")

    def test_inbox_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("inbox"))
        self.assertRedirects(response, f"/login/?next={reverse('inbox')}")

    def test_expired_htmx_session_redirects_the_whole_page(self):
        self.client.logout()
        response = self.client.get(reverse("inbox"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["HX-Redirect"], f"/login/?next={reverse('inbox')}")

    def test_filter_conditions_are_combined(self):
        response = self.client.get(reverse("inbox"), {"tag": self.tag.pk, "source": Lead.Source.MANUAL, "status": Lead.Status.NEW, "q": "Сайтова"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Анна Сайтова")
        self.assertNotContains(response, "Борис Рекламов")

    def test_tag_badges_render_a_stable_individual_color(self):
        response = self.client.get(reverse("inbox"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'class="tag-chip tag-color-{(self.tag.pk - 1) % 8}"')
        second_tag = self.second.tags.get()
        self.assertContains(response, f'class="tag-chip tag-color-{(second_tag.pk - 1) % 8}"')

    def test_sidebar_sections_collapse_and_expand_to_all_tags(self):
        for number in range(5):
            add_lead_tag(lead=self.second, value=f"Дополнительный {number}")
        response = self.client.get(reverse("inbox"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-persist-disclosure="funnel"')
        self.assertContains(response, 'data-persist-disclosure="tags"')
        self.assertContains(response, "Показать все теги (+4)")
        self.assertContains(response, "Дополнительный 4")

    def test_htmx_status_change_renders_updated_card_and_keeps_filters(self):
        response = self.client.post(
            reverse("lead_status", args=[self.first.pk]),
            {"status": Lead.Status.IN_PROGRESS},
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL=f"http://testserver{reverse('inbox')}?q=Анна&tag={self.tag.pk}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сохранено")
        self.assertContains(response, f"tag%3D{self.tag.pk}")
        self.first.refresh_from_db()
        self.assertEqual(self.first.status, Lead.Status.IN_PROGRESS)

    def test_htmx_invalid_tag_shows_inline_error(self):
        response = self.client.post(
            reverse("lead_add_tag", args=[self.first.pk]),
            {"tag": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тег должен содержать от 1 до 32 символов.")
        self.assertEqual(self.first.tags.count(), 1)

    def test_drawer_request_returns_only_the_card_and_keeps_list_url(self):
        response = self.client.get(
            reverse("inbox"),
            {"tag": self.tag.pk, "q": "Анна", "selected": self.first.pk},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="drawer-host",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "data-drawer-backdrop")
        self.assertContains(response, "tag=1")
        self.assertNotContains(response, "class=\"leads-table\"")

    def test_manual_form_creates_normalized_tags_atomically(self):
        token = uuid.uuid4()
        response = self.client.post(reverse("lead_new"), {
            "submission_id": str(token), "return_to": reverse("inbox"), "name": "Новая заявка",
            "contact_type": "email", "contact_value": "new@example.com",
            "request": "Нужен сайт агентства.", "tags": " ＃ SEO, seo, Дизайн ",
        })
        self.assertEqual(response.status_code, 302)
        lead = Lead.objects.get(submission_id=token)
        self.assertEqual(set(lead.tags.values_list("name", flat=True)), {"SEO", "Дизайн"})

    def test_manual_form_creates_deal_in_selected_stage_with_amount(self):
        token = uuid.uuid4()
        response = self.client.post(reverse("lead_new") + "?stage=proposal_sent&return_to=%2Fboard%2F", {
            "submission_id": str(token), "return_to": "/board/", "initial_status": Lead.Status.PROPOSAL_SENT,
            "name": "Новая сделка", "contact_type": "email", "contact_value": "deal@example.com",
            "request": "Нужна рекламная кампания.", "deal_amount": "245000.50", "tags": "",
        })
        self.assertRedirects(response, reverse("board"))
        lead = Lead.objects.get(submission_id=token)
        self.assertEqual(lead.status, Lead.Status.PROPOSAL_SENT)
        self.assertEqual(lead.deal_amount, Decimal("245000.50"))

    def test_board_sums_deal_amounts_and_links_to_stage_prefilled_creation(self):
        Lead.objects.filter(pk=self.first.pk).update(deal_amount=Decimal("125000.00"))
        Lead.objects.filter(pk=self.second.pk).update(deal_amount=Decimal("50000.00"))
        response = self.client.get(reverse("board"))
        self.assertEqual(response.status_code, 200)
        new_column = next(column for column in response.context["columns"] if column["value"] == Lead.Status.NEW)
        self.assertEqual(new_column["amount_total"], Decimal("175000.00"))
        self.assertContains(response, "Добавить сделку")
        self.assertContains(response, "Сумма сделок:")
        self.assertContains(response, "175 000 ₽")
        self.assertContains(response, "stage=new&amp;return_to=%2Fboard%2F")

    def test_deal_amount_can_be_saved_in_lead_card_and_reject_negative_value(self):
        url = reverse("lead_amount", args=[self.first.pk])
        invalid = self.client.post(
            url, {"deal_amount": "-1"}, HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="selected-lead", HTTP_HX_CURRENT_URL=f"http://testserver/leads/{self.first.pk}/",
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Укажите сумму от нуля")
        self.first.refresh_from_db()
        self.assertIsNone(self.first.deal_amount)

        saved = self.client.post(
            url, {"deal_amount": "87650"}, HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="selected-lead", HTTP_HX_CURRENT_URL=f"http://testserver/leads/{self.first.pk}/",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertContains(saved, "Сумма сделки сохранена")
        self.assertContains(saved, "87 650 ₽")
        self.first.refresh_from_db()
        self.assertEqual(self.first.deal_amount, Decimal("87650.00"))

    def test_channel_status_does_not_expose_a_bot_token(self):
        from django.test import override_settings

        with override_settings(BOT_TOKEN="secret-test-token-that-must-not-render", BOT_USERNAME="potok_demo_bot"):
            response = self.client.get(reverse("channels"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@potok_demo_bot")
        self.assertContains(response, "Не проверено")
        self.assertNotContains(response, "secret-test-token-that-must-not-render")

    def test_channel_page_does_not_link_to_non_https_public_url(self):
        from django.test import override_settings

        with override_settings(PUBLIC_BASE_URL="javascript:alert(1)"):
            response = self.client.get(reverse("channels"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HTTPS ещё не настроены")
        self.assertNotContains(response, "javascript:")

    def test_board_shows_every_funnel_stage_and_can_move_a_lead(self):
        response = self.client.get(reverse("board"))
        self.assertEqual(response.status_code, 200)
        for _, label in Lead.Status.choices:
            self.assertContains(response, label)
        moved = self.client.post(
            reverse("lead_status", args=[self.first.pk]),
            {"status": Lead.Status.QUALIFIED},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="kanban-board",
        )
        self.assertEqual(moved.status_code, 200)
        self.assertContains(moved, "Анна Сайтова")
        self.assertContains(moved, 'class="kanban-board"')
        self.assertNotContains(moved, 'class="lead-card"')
        self.first.refresh_from_db()
        self.assertEqual(self.first.status, Lead.Status.QUALIFIED)
        invalid = self.client.post(
            reverse("lead_status", args=[self.first.pk]),
            {"status": "not-a-status"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="kanban-board",
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Неизвестный статус.")
        self.assertContains(invalid, 'class="kanban-board"')

    def test_calendar_lists_scheduled_follow_up_dates(self):
        scheduled = timezone.localdate() + timedelta(days=1)
        self.first.next_contact_date = scheduled
        self.first.save(update_fields=["next_contact_date"])
        response = self.client.get(reverse("calendar"), {"month": scheduled.strftime("%Y-%m")})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Анна Сайтова")

    def test_calendar_uses_russian_month_names_in_ui_and_accessible_labels(self):
        response = self.client.get(reverse("calendar"), {"month": "2026-10"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Октябрь 2026")
        self.assertContains(response, 'aria-label="28 сентября:')
        self.assertNotContains(response, "October 2026")

    def test_lead_detail_returns_to_the_calendar_month(self):
        response = self.client.get(
            reverse("lead_detail", args=[self.first.pk]),
            {"return_to": "/calendar/?month=2026-10"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/calendar/?month=2026-10"')
        self.assertContains(response, "← К календарю")

    def test_next_contact_date_is_saved_through_existing_lead_service(self):
        scheduled = timezone.localdate() + timedelta(days=2)
        response = self.client.post(
            reverse("lead_next_contact", args=[self.first.pk]),
            {"next_contact_date": scheduled.strftime("%Y-%m-%d")},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="selected-lead",
            HTTP_HX_CURRENT_URL="http://testserver/leads/1/",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дата следующего контакта сохранена")
        self.first.refresh_from_db()
        self.assertEqual(self.first.next_contact_date, scheduled)

    def test_new_manual_form_uses_submission_uuid(self):
        token = uuid.uuid4()
        data = {
            "submission_id": str(token), "name": "Ручная заявка", "contact_type": "email",
            "contact_value": "manual@example.com", "request": "Проверка ручной формы.",
        }
        first = self.client.post(reverse("lead_new"), data)
        second = self.client.post(reverse("lead_new"), data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Lead.objects.filter(submission_id=token).count(), 1)
