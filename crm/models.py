import uuid

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator


class Tag(models.Model):
    name = models.CharField(max_length=32)
    normalized_name = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["normalized_name"]

    def __str__(self):
        return self.name


class Lead(models.Model):
    class Source(models.TextChoices):
        BOT = "bot", "Бот"
        MANUAL = "manual", "Вручную"
        TELEGRAM = "telegram", "Telegram"

    class Status(models.TextChoices):
        NEW = "new", "Новая заявка"
        QUALIFIED = "qualified", "Квалифицирована"
        BRIEFING = "briefing", "Брифинг"
        PROPOSAL_SENT = "proposal_sent", "КП отправлено"
        NEGOTIATION = "negotiation", "Переговоры"
        IN_PROGRESS = "in_progress", "В работе"
        WAITING = "waiting", "Ожидание клиента"
        CLOSED = "closed", "Успешно завершена"
        LOST = "lost", "Отказ"

    name = models.CharField("Имя", max_length=100)
    contact_type = models.CharField("Тип контакта", max_length=16, choices=[("phone", "Телефон"), ("email", "Email"), ("telegram", "Telegram")])
    contact_value = models.CharField("Контакт", max_length=200)
    request = models.TextField("Запрос", max_length=3000)
    deal_amount = models.DecimalField("Сумма сделки", max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    next_contact_date = models.DateField("Следующий контакт", null=True, blank=True, db_index=True)
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    telegram_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    tags = models.ManyToManyField(Tag, through="LeadTag", related_name="leads", blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Заявка №{self.pk}: {self.name}"


class LeadTag(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead", "tag"], name="unique_lead_tag")]


class IntakeSession(models.Model):
    class Step(models.TextChoices):
        NAME = "name", "Имя"
        CONTACT = "contact", "Контакт"
        REQUEST = "request", "Задача"
        REVIEW = "review", "Подтверждение"
        SUBMITTED = "submitted", "Отправлена"
        CANCELLED = "cancelled", "Отменена"

    bot_id = models.BigIntegerField()
    chat_id = models.BigIntegerField()
    user_id = models.BigIntegerField()
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True)
    step = models.CharField(max_length=16, choices=Step.choices, default=Step.NAME)
    validated_data = models.JSONField(default=dict, blank=True)
    last_lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="intake_sessions")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["bot_id", "chat_id", "user_id"], name="unique_intake_actor")]


class UpdateReceipt(models.Model):
    integration_key = models.CharField(max_length=32, default="bot")
    external_update_id = models.CharField(max_length=128)
    processed_at = models.DateTimeField(auto_now_add=True)
    result_lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["integration_key", "external_update_id"], name="unique_update_receipt")]


class Activity(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=24)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
