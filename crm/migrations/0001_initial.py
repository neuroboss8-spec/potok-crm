import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="Имя")),
                ("contact_type", models.CharField(choices=[("phone", "Телефон"), ("email", "Email"), ("telegram", "Telegram")], max_length=16, verbose_name="Тип контакта")),
                ("contact_value", models.CharField(max_length=200, verbose_name="Контакт")),
                ("request", models.TextField(max_length=3000, verbose_name="Запрос")),
                ("source", models.CharField(choices=[("bot", "Бот"), ("manual", "Вручную"), ("telegram", "Telegram")], default="manual", max_length=16)),
                ("status", models.CharField(choices=[("new", "Новая"), ("in_progress", "В работе"), ("closed", "Закрыта")], default="new", max_length=16)),
                ("submission_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("telegram_user_id", models.BigIntegerField(blank=True, db_index=True, null=True)),
                ("is_demo", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=32)),
                ("normalized_name", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["normalized_name"]},
        ),
        migrations.CreateModel(
            name="LeadTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.lead")),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.tag")),
            ],
        ),
        migrations.AddField(
            model_name="lead",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="leads", through="crm.LeadTag", to="crm.tag"),
        ),
        migrations.AddConstraint(
            model_name="leadtag",
            constraint=models.UniqueConstraint(fields=("lead", "tag"), name="unique_lead_tag"),
        ),
        migrations.CreateModel(
            name="IntakeSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bot_id", models.BigIntegerField()),
                ("chat_id", models.BigIntegerField()),
                ("user_id", models.BigIntegerField()),
                ("submission_id", models.UUIDField(default=uuid.uuid4, unique=True)),
                ("step", models.CharField(choices=[("name", "Имя"), ("contact", "Контакт"), ("request", "Задача"), ("review", "Подтверждение"), ("submitted", "Отправлена"), ("cancelled", "Отменена")], default="name", max_length=16)),
                ("validated_data", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_lead", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="intake_sessions", to="crm.lead")),
            ],
        ),
        migrations.AddConstraint(
            model_name="intakesession",
            constraint=models.UniqueConstraint(fields=("bot_id", "chat_id", "user_id"), name="unique_intake_actor"),
        ),
        migrations.CreateModel(
            name="UpdateReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("integration_key", models.CharField(default="bot", max_length=32)),
                ("external_update_id", models.CharField(max_length=128)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                ("result_lead", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="crm.lead")),
            ],
        ),
        migrations.AddConstraint(
            model_name="updatereceipt",
            constraint=models.UniqueConstraint(fields=("integration_key", "external_update_id"), name="unique_update_receipt"),
        ),
        migrations.CreateModel(
            name="Activity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=24)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="crm.lead")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]

