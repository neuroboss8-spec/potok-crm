import logging
import re
import uuid
from datetime import timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery, ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from .models import IntakeSession, Lead, UpdateReceipt
from .services import complete_intake, contact_is_valid, record_receipt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("potok.bot")
GREETING = {"здравствуйте", "здравствуй", "привет", "добрый день", "доброе утро", "добрый вечер", "хай", "hello", "hi"}
CONTACT_LABEL = {"phone": "Телефон", "email": "Email", "telegram": "Telegram"}
STEP_PROMPT = {
    IntakeSession.Step.NAME: "Как к вам обращаться? Можно оставить предложенное имя или написать другое.",
    IntakeSession.Step.CONTACT: "Выберите тип контакта: телефон с кодом страны (+...), email или Telegram.",
    IntakeSession.Step.REQUEST: "Коротко опишите задачу (от 5 до 3000 символов).",
}


def actor_query(bot_id, chat_id, user_id):
    return IntakeSession.objects.filter(bot_id=bot_id, chat_id=chat_id, user_id=user_id)


@sync_to_async(thread_sensitive=True)
def begin(bot_id, chat_id, user_id, suggested_name, first_request, update_id, restart=False):
    with transaction.atomic():
        if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
            return "duplicate", None
        session = actor_query(bot_id, chat_id, user_id).select_for_update().first()
        active = session and session.step not in (IntakeSession.Step.SUBMITTED, IntakeSession.Step.CANCELLED)
        recent = session and timezone.now() - session.updated_at <= timedelta(hours=24)
        if active and recent and not restart:
            record_receipt(update_id)
            return "resume_prompt", session
        session = session or IntakeSession(bot_id=bot_id, chat_id=chat_id, user_id=user_id)
        session.submission_id = uuid.uuid4()
        session.step = IntakeSession.Step.NAME
        session.validated_data = {"name": suggested_name[:100]}
        if first_request and first_request not in GREETING and 5 <= len(first_request) <= 3000:
            session.validated_data["request"] = first_request
        else:
            session.validated_data.pop("request", None)
        session.save()
        record_receipt(update_id)
        return "started", session


@sync_to_async(thread_sensitive=True)
def load_session(bot_id, chat_id, user_id):
    return actor_query(bot_id, chat_id, user_id).first()


@sync_to_async(thread_sensitive=True)
def cancel_session(bot_id, chat_id, user_id, update_id):
    with transaction.atomic():
        if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
            return False
        session = actor_query(bot_id, chat_id, user_id).select_for_update().first()
        if session and session.step not in (IntakeSession.Step.SUBMITTED, IntakeSession.Step.CANCELLED):
            session.step = IntakeSession.Step.CANCELLED
            session.save(update_fields=["step", "updated_at"])
        record_receipt(update_id)
        return True


@sync_to_async(thread_sensitive=True)
def show_status(bot_id, chat_id, user_id, update_id):
    if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
        return "duplicate"
    session = actor_query(bot_id, chat_id, user_id).select_related("last_lead").first()
    record_receipt(update_id)
    if session and session.step == IntakeSession.Step.SUBMITTED and session.last_lead_id:
        return f"Последняя заявка: №{session.last_lead_id}."
    if session and session.step not in (IntakeSession.Step.CANCELLED, IntakeSession.Step.SUBMITTED):
        return "Текущий шаг: " + STEP_PROMPT.get(session.step, "проверьте сводку и подтвердите заявку.")
    if session and session.last_lead_id:
        return f"Последняя заявка: №{session.last_lead_id}."
    return "Активной анкеты нет. Напишите /start, чтобы оставить заявку."


@sync_to_async(thread_sensitive=True)
def choose_contact(bot_id, chat_id, user_id, kind, update_id):
    with transaction.atomic():
        if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
            return None, "duplicate"
        session = actor_query(bot_id, chat_id, user_id).select_for_update().first()
        if not session or session.step != IntakeSession.Step.CONTACT:
            record_receipt(update_id)
            return None, "Анкета уже изменилась. Нажмите /status и продолжите актуальный шаг."
        data = session.validated_data
        data["contact_type"] = kind
        data.pop("contact_value", None)
        session.validated_data = data
        session.save(update_fields=["validated_data", "updated_at"])
        record_receipt(update_id)
        return session, "ok"


@sync_to_async(thread_sensitive=True)
def change_step(bot_id, chat_id, user_id, step, update_id):
    with transaction.atomic():
        if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
            return None
        session = actor_query(bot_id, chat_id, user_id).select_for_update().first()
        if session and session.step == IntakeSession.Step.REVIEW and step in (IntakeSession.Step.NAME, IntakeSession.Step.CONTACT, IntakeSession.Step.REQUEST):
            session.step = step
            session.save(update_fields=["step", "updated_at"])
        record_receipt(update_id)
        return session


@sync_to_async(thread_sensitive=True)
def accept_shared_contact(bot_id, chat_id, user_id, phone, contact_owner, update_id):
    with transaction.atomic():
        if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
            return None, "duplicate"
        session = actor_query(bot_id, chat_id, user_id).select_for_update().first()
        if not session or session.step != IntakeSession.Step.CONTACT or session.validated_data.get("contact_type") != "phone":
            record_receipt(update_id)
            return None, "Сначала выберите телефон как тип контакта."
        if contact_owner != user_id or not contact_is_valid("phone", phone):
            record_receipt(update_id)
            return None, "Номер должен принадлежать вашему Telegram-профилю и иметь корректный формат."
        data = session.validated_data
        data.update({"contact_value": re.sub(r"\s+", " ", phone).strip(), "request": data.get("request", "")})
        session.validated_data = data
        session.step = IntakeSession.Step.REQUEST if not data.get("request") else IntakeSession.Step.REVIEW
        session.save(update_fields=["validated_data", "step", "updated_at"])
        record_receipt(update_id)
        return session, "ok"


@sync_to_async(thread_sensitive=True)
def save_text(bot_id, chat_id, user_id, text, update_id, suggested_name="", first_message=False):
    with transaction.atomic():
        if UpdateReceipt.objects.filter(integration_key="bot", external_update_id=str(update_id)).exists():
            return None, "duplicate"
        session = actor_query(bot_id, chat_id, user_id).select_for_update().first()
        if not session and first_message:
            session = IntakeSession(bot_id=bot_id, chat_id=chat_id, user_id=user_id,
                                    validated_data={"request": text} if text.casefold().strip(".! ") not in GREETING and 5 <= len(text) <= 3000 else {},
                                    step=IntakeSession.Step.NAME)
            session.save()
            record_receipt(update_id)
            return session, "ok"
        if not session:
            record_receipt(update_id)
            return None, "Напишите /start, чтобы начать."
        if timezone.now() - session.updated_at > timedelta(hours=24) and session.step not in (IntakeSession.Step.SUBMITTED, IntakeSession.Step.CANCELLED):
            session.step = IntakeSession.Step.NAME
            session.validated_data = {}
        data = dict(session.validated_data)
        current = session.step
        response = "ok"
        if current == IntakeSession.Step.NAME:
            value = text.strip()
            if not value or len(value) > 100:
                response = "Имя должно содержать от 1 до 100 символов. Попробуйте ещё раз."
            else:
                data["name"] = value
                session.step = IntakeSession.Step.REVIEW if data.get("contact_value") and data.get("request") else IntakeSession.Step.CONTACT
        elif current == IntakeSession.Step.CONTACT:
            kind = data.get("contact_type")
            value = text.strip()
            if not kind:
                response = "Сначала выберите тип контакта на кнопках ниже."
            elif len(value) > 200 or not contact_is_valid(kind, value):
                response = "Проверьте контакт и отправьте его ещё раз. Номер телефона укажите с кодом страны, например +7..."
            else:
                data["contact_value"] = value
                session.step = IntakeSession.Step.REQUEST if not data.get("request") else IntakeSession.Step.REVIEW
        elif current == IntakeSession.Step.REQUEST:
            value = text.strip()
            if len(value) < 5 or len(value) > 3000:
                response = "Описание должно содержать от 5 до 3000 символов. Я ничего не обрезал; попробуйте ещё раз."
            else:
                data["request"] = value
                session.step = IntakeSession.Step.REVIEW
        elif current == IntakeSession.Step.REVIEW:
            response = "Проверьте сводку и выберите «Отправить» или «Изменить поле»."
        elif current == IntakeSession.Step.SUBMITTED:
            response = f"Последняя заявка №{session.last_lead_id} уже принята. Новую начните командой /start."
        else:
            response = "Анкета отменена. Напишите /start, чтобы начать заново."
        session.validated_data = data
        session.save(update_fields=["validated_data", "step", "updated_at"])
        record_receipt(update_id)
        return session, response


def review_messages(session):
    data = session.validated_data
    request = data.get("request", "")
    contact = data.get("contact_value", "")
    messages = [f"Проверьте заявку:\n\nИмя: {data.get('name', '—')}\nКонтакт ({CONTACT_LABEL.get(data.get('contact_type'), '—')}): {contact}\n\nЗадача:"]
    chunk, units = "", 0
    for char in request:
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > 3000:
            messages.append(chunk)
            chunk, units = "", 0
        chunk += char
        units += size
    if chunk or not request:
        messages.append(chunk or "—")
    messages.append("Отправить заявку?")
    return messages


def review_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить", callback_data="submit")],
        [InlineKeyboardButton(text="Изменить имя", callback_data="edit:name"), InlineKeyboardButton(text="Изменить контакт", callback_data="edit:contact")],
        [InlineKeyboardButton(text="Изменить задачу", callback_data="edit:request")],
    ])


def contact_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поделиться телефоном", callback_data="contact:phone")],
        [InlineKeyboardButton(text="Email", callback_data="contact:email"), InlineKeyboardButton(text="Telegram", callback_data="contact:telegram")],
    ])


async def send_review(target, session):
    parts = review_messages(session)
    for part in parts[:-1]:
        await target.answer(part)
    await target.answer(parts[-1], reply_markup=review_keyboard())


async def run(token):
    bot = Bot(token=token)
    identity = await bot.get_me()
    bot_id = identity.id
    dp = Dispatcher()

    @dp.errors()
    async def on_unhandled_error(event: ErrorEvent):
        update_id = getattr(event.update, "update_id", "unknown")
        logger.error("telegram update failed update_id=%s error_type=%s", update_id, type(event.exception).__name__)
        try:
            if event.update.callback_query:
                await event.update.callback_query.answer("Не удалось завершить действие. Проверьте /status и повторите при необходимости.", show_alert=True)
            elif event.update.message:
                await event.update.message.answer("Не удалось сохранить сообщение. Отправьте его ещё раз или проверьте /status.")
        except Exception:
            pass
        return True

    @dp.message(CommandStart())
    async def on_start(message: Message):
        first = message.text.partition(" ")[2].strip()
        if first and len(first) >= 5:
            state, session = await begin(bot_id, message.chat.id, message.from_user.id, message.from_user.full_name, first, f"{message.chat.id}:{message.message_id}")
        else:
            session = await load_session(bot_id, message.chat.id, message.from_user.id)
            if session and session.step not in (IntakeSession.Step.SUBMITTED, IntakeSession.Step.CANCELLED) and timezone.now() - session.updated_at <= timedelta(hours=24):
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Продолжить", callback_data="resume"), InlineKeyboardButton(text="Начать заново", callback_data="restart")]])
                await message.answer("У вас есть незавершённая анкета. Продолжить или начать заново?", reply_markup=kb)
                return
            state, session = await begin(bot_id, message.chat.id, message.from_user.id, message.from_user.full_name, "", f"{message.chat.id}:{message.message_id}", restart=True)
        if state == "duplicate":
            return
        session = await load_session(bot_id, message.chat.id, message.from_user.id)
        await message.answer("Оставьте заявку в Поток CRM: укажите имя, контакт и задачу. Перед отправкой вы сможете проверить данные.\n\n" + STEP_PROMPT.get(session.step, "Продолжим с текущего шага."))
        if session.step == IntakeSession.Step.CONTACT:
            await message.answer("Выберите тип контакта:", reply_markup=contact_keyboard())
        elif session.step == IntakeSession.Step.REVIEW:
            await send_review(message, session)

    @dp.message(Command("cancel"))
    async def on_cancel(message: Message):
        if await cancel_session(bot_id, message.chat.id, message.from_user.id, f"{message.chat.id}:{message.message_id}"):
            await message.answer("Незавершённая анкета отменена. Сохранённые заявки остаются без изменений.")

    @dp.message(Command("status"))
    async def on_status(message: Message):
        status = await show_status(bot_id, message.chat.id, message.from_user.id, f"{message.chat.id}:{message.message_id}")
        if status != "duplicate":
            await message.answer(status)

    @dp.callback_query(F.data.in_({"resume", "restart"}))
    async def on_resume(callback: CallbackQuery):
        session = await load_session(bot_id, callback.message.chat.id, callback.from_user.id)
        if callback.data == "restart" or not session:
            await begin(bot_id, callback.message.chat.id, callback.from_user.id, callback.from_user.full_name, "", callback.id, restart=True)
            session = await load_session(bot_id, callback.message.chat.id, callback.from_user.id)
        await callback.answer()
        if session.step == IntakeSession.Step.REVIEW:
            await send_review(callback.message, session)
        elif session.step == IntakeSession.Step.CONTACT:
            await callback.message.answer(STEP_PROMPT[session.step], reply_markup=contact_keyboard())
        else:
            await callback.message.answer(STEP_PROMPT.get(session.step, "Анкета уже отправлена."))

    @dp.callback_query(F.data.startswith("contact:"))
    async def on_contact_type(callback: CallbackQuery):
        kind = callback.data.split(":", 1)[1]
        session, result = await choose_contact(bot_id, callback.message.chat.id, callback.from_user.id, kind, callback.id)
        await callback.answer()
        if result != "ok":
            if result != "duplicate":
                await callback.message.answer(result)
            return
        if kind == "phone":
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Поделиться моим номером", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
            await callback.message.answer("Нажмите кнопку, чтобы поделиться номером, или введите номер с кодом страны.", reply_markup=kb)
        else:
            await callback.message.answer("Укажите email адрес." if kind == "email" else "Укажите свой username в Telegram, например @example.", reply_markup=ReplyKeyboardRemove())

    @dp.message(F.contact)
    async def on_shared_contact(message: Message):
        session, result = await accept_shared_contact(bot_id, message.chat.id, message.from_user.id,
                                                       message.contact.phone_number, message.contact.user_id, f"{message.chat.id}:{message.message_id}")
        if result == "duplicate":
            return
        if result != "ok":
            await message.answer(result)
            return
        if session.step == IntakeSession.Step.REQUEST:
            await message.answer(STEP_PROMPT[IntakeSession.Step.REQUEST], reply_markup=ReplyKeyboardRemove())
        else:
            await send_review(message, session)

    @dp.callback_query(F.data.startswith("edit:"))
    async def on_edit(callback: CallbackQuery):
        field = callback.data.split(":", 1)[1]
        step = {"name": IntakeSession.Step.NAME, "contact": IntakeSession.Step.CONTACT, "request": IntakeSession.Step.REQUEST}.get(field)
        session = await change_step(bot_id, callback.message.chat.id, callback.from_user.id, step, callback.id) if step else None
        await callback.answer()
        if session:
            if step == IntakeSession.Step.CONTACT:
                await callback.message.answer("Выберите тип контакта заново:", reply_markup=contact_keyboard())
            else:
                await callback.message.answer(STEP_PROMPT[step])
        else:
            await callback.message.answer("Анкета изменилась. Напишите /status и продолжите актуальный шаг.")

    @dp.callback_query(F.data == "submit")
    async def on_submit(callback: CallbackQuery):
        session = await load_session(bot_id, callback.message.chat.id, callback.from_user.id)
        if not session:
            await callback.answer("Анкета уже изменилась.", show_alert=True)
            return
        try:
            lead, created = await sync_to_async(complete_intake, thread_sensitive=True)(session_id=session.pk, update_id=callback.id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await callback.answer("Заявка принята" if created else "Уже сохранено")
        await callback.message.answer(f"Заявка №{lead.pk} принята." if created else f"Эта заявка уже сохранена: №{lead.pk}.")

    @dp.message(F.text)
    async def on_text(message: Message):
        text = message.text.strip()
        # Avoid treating a conversation's exact greeting as the original request.
        first = await load_session(bot_id, message.chat.id, message.from_user.id) is None
        session, response = await save_text(bot_id, message.chat.id, message.from_user.id, text, f"{message.chat.id}:{message.message_id}",
                                            message.from_user.full_name, first_message=first)
        if response == "duplicate":
            return
        if response != "ok":
            await message.answer(response)
            return
        if session.step == IntakeSession.Step.CONTACT:
            await message.answer("Теперь выберите тип контакта:", reply_markup=contact_keyboard())
        elif session.step == IntakeSession.Step.REVIEW:
            await send_review(message, session)
        else:
            await message.answer(STEP_PROMPT.get(session.step, "Продолжайте анкету."))

    @dp.message()
    async def on_unsupported(message: Message):
        await message.answer("Пока принимаю только текст. Черновик сохранён; отправьте ответ для текущего шага.")

    logger.info("bot worker started bot_id=%s", bot_id)
    await dp.start_polling(bot, handle_as_tasks=False, allowed_updates=dp.resolve_used_update_types())
