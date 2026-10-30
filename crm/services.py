import re
import unicodedata
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Activity, IntakeSession, Lead, LeadTag, Tag, UpdateReceipt


def normalize_tag(value):
    name = " ".join(unicodedata.normalize("NFKC", value).strip().lstrip("#").split())
    if not name or len(name) > 32:
        raise ValueError("Тег должен содержать от 1 до 32 символов.")
    return name, name.casefold()


def get_or_create_tag(value):
    name, normalized = normalize_tag(value)
    tag, created = Tag.objects.get_or_create(normalized_name=normalized, defaults={"name": name})
    return tag, created


@transaction.atomic
def create_lead(*, data, source=Lead.Source.MANUAL, submission_id=None, telegram_user_id=None, tags=(), actor=None, is_demo=False):
    submission_id = submission_id or uuid.uuid4()
    existing = Lead.objects.filter(submission_id=submission_id).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            lead = Lead.objects.create(
                name=data["name"].strip(), contact_type=data["contact_type"], contact_value=data["contact_value"].strip(),
                request=data["request"].strip(), deal_amount=data.get("deal_amount") if "deal_amount" in data else None,
                source=source, submission_id=submission_id,
                telegram_user_id=telegram_user_id, is_demo=is_demo,
            )
    except IntegrityError:
        existing = Lead.objects.filter(submission_id=submission_id).first()
        if existing:
            return existing, False
        raise
    for value in tags:
        tag, _ = get_or_create_tag(value)
        LeadTag.objects.get_or_create(lead=lead, tag=tag)
    Activity.objects.create(lead=lead, kind="created", actor=actor, details={"source": source})
    return lead, True


@transaction.atomic
def update_lead(*, lead, data, actor=None):
    changed = {}
    for field in ("name", "contact_type", "contact_value", "request", "deal_amount"):
        if field not in data:
            continue
        value = data[field].strip() if isinstance(data[field], str) else data[field]
        if getattr(lead, field) != value:
            changed[field] = True
            setattr(lead, field, value)
    if changed:
        lead.save(update_fields=[*changed.keys(), "updated_at"])
        Activity.objects.create(lead=lead, kind="edited", actor=actor, details={"fields": list(changed)})
    return lead


@transaction.atomic
def set_deal_amount(*, lead, value, actor=None):
    return update_lead(lead=lead, data={"deal_amount": value}, actor=actor)


@transaction.atomic
def set_lead_status(*, lead, status, actor=None):
    if status not in Lead.Status.values:
        raise ValueError("Неизвестный статус.")
    if lead.status != status:
        old = lead.status
        lead.status = status
        lead.save(update_fields=["status", "updated_at"])
        Activity.objects.create(lead=lead, kind="status", actor=actor, details={"from": old, "to": status})


@transaction.atomic
def set_next_contact_date(*, lead, value, actor=None):
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if lead.next_contact_date != value:
        previous = lead.next_contact_date.isoformat() if lead.next_contact_date else ""
        lead.next_contact_date = value
        lead.save(update_fields=["next_contact_date", "updated_at"])
        Activity.objects.create(
            lead=lead,
            kind="follow_up",
            actor=actor,
            details={"from": previous, "to": value.isoformat() if value else ""},
        )
    return lead


@transaction.atomic
def add_lead_tag(*, lead, value, actor=None):
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    tag, _ = get_or_create_tag(value)
    if lead.tags.count() >= 6 and not lead.tags.filter(pk=tag.pk).exists():
        raise ValueError("На одну заявку можно назначить не больше шести тегов.")
    _, created = LeadTag.objects.get_or_create(lead=lead, tag=tag)
    if created:
        Activity.objects.create(lead=lead, kind="tag_added", actor=actor, details={"tag": tag.name})
    return tag, created


@transaction.atomic
def remove_lead_tag(*, lead, tag_id, actor=None):
    edge = LeadTag.objects.select_for_update().filter(lead=lead, tag_id=tag_id).select_related("tag").first()
    if edge:
        label = edge.tag.name
        edge.delete()
        Activity.objects.create(lead=lead, kind="tag_removed", actor=actor, details={"tag": label})


@transaction.atomic
def record_receipt(external_update_id, lead=None, integration_key="bot"):
    try:
        receipt, created = UpdateReceipt.objects.get_or_create(
            integration_key=integration_key, external_update_id=str(external_update_id), defaults={"result_lead": lead}
        )
        return receipt, created
    except IntegrityError:
        return UpdateReceipt.objects.get(integration_key=integration_key, external_update_id=str(external_update_id)), False


@transaction.atomic
def complete_intake(*, session_id, update_id):
    session = IntakeSession.objects.select_for_update().get(pk=session_id)
    prior = UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).first()
    if prior and prior.result_lead_id:
        return prior.result_lead, False
    if session.step == IntakeSession.Step.SUBMITTED and session.last_lead_id:
        record_receipt(update_id, session.last_lead)
        return session.last_lead, False
    data = session.validated_data
    if session.step != IntakeSession.Step.REVIEW or not {"name", "contact_type", "contact_value", "request"}.issubset(data):
        raise ValueError("Анкета изменилась. Отправьте /start, чтобы начать заново.")
    recent = Lead.objects.filter(
        telegram_user_id=session.user_id, source=Lead.Source.BOT,
        created_at__gte=timezone.now() - timedelta(hours=1),
    ).count()
    if recent >= 5:
        raise ValueError("Можно отправить не больше пяти заявок в час. Попробуйте позже.")
    lead, _ = create_lead(data=data, source=Lead.Source.BOT, submission_id=session.submission_id, telegram_user_id=session.user_id)
    session.step = IntakeSession.Step.SUBMITTED
    session.last_lead = lead
    session.save(update_fields=["step", "last_lead", "updated_at"])
    receipt, _ = record_receipt(update_id, lead)
    if receipt.result_lead_id != lead.pk:
        receipt.result_lead = lead
        receipt.save(update_fields=["result_lead"])
    return lead, True


def contact_is_valid(contact_type, value):
    if contact_type == "email":
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        try:
            validate_email(value)
            return len(value) <= 200
        except ValidationError:
            return False
    if contact_type == "phone":
        digits = re.sub(r"\D", "", value)
        return value.lstrip().startswith("+") and 8 <= len(digits) <= 15 and bool(re.fullmatch(r"[+()\d\s.\-]+", value))
    if contact_type == "telegram":
        return bool(re.fullmatch(r"@?[A-Za-z0-9_]{5,32}", value))
    return False
