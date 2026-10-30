from calendar import Calendar as MonthCalendar
from datetime import date, timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.http import QueryDict
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .forms import DealAmountForm, LeadForm, NextContactForm
from .models import Lead, Tag
from .services import add_lead_tag, create_lead, remove_lead_tag, set_deal_amount, set_lead_status, set_next_contact_date, update_lead


def _base_queryset():
    return Lead.objects.prefetch_related("tags").order_by("-created_at", "-id")


def _filter_values(params):
    query = params.get("q", "").strip()[:100]
    tag = params.get("tag", "")
    if not tag.isdecimal() or len(tag) > 12 or not Tag.objects.filter(pk=int(tag)).exists():
        tag = ""
    source = params.get("source", "")
    if source not in Lead.Source.values:
        source = ""
    status = params.get("status", "")
    if status not in Lead.Status.values:
        status = ""
    return {"q": query, "tag": tag, "source": source, "status": status}


def _page_value(params):
    page = params.get("page", "")
    return page if page.isdecimal() and len(page) <= 6 and int(page) > 1 else None


def _list_url(filters, *, page=None, selected=None):
    params = QueryDict("", mutable=True)
    for key in ("q", "tag", "source", "status"):
        if filters.get(key):
            params[key] = filters[key]
    if page:
        params["page"] = str(page)
    if selected:
        params["selected"] = str(selected)
    query = params.urlencode()
    return reverse("inbox") + (f"?{query}" if query else "")


def _detail_context(lead, *, filters=None, page=None, detail_target="#selected-lead"):
    filters = filters or {"q": "", "tag": "", "source": "", "status": ""}
    query = filters.get("q", "").casefold()
    matches = (
        (not filters.get("tag") or lead.tags.filter(pk=filters["tag"]).exists())
        and (not filters.get("source") or lead.source == filters["source"])
        and (not filters.get("status") or lead.status == filters["status"])
        and (not query or any(query in value.casefold() for value in (lead.name, lead.contact_value, lead.request)))
    )
    return {
        "lead": lead,
        "tag_choices": Tag.objects.all(),
        "status_choices": Lead.Status.choices,
        "detail_target": detail_target,
        "list_url": _list_url(filters, page=page),
        "selected_url": _list_url(filters, page=page, selected=lead.pk),
        "list_label": "← К заявкам",
        "card_outside_filter": not matches,
        "next_contact_form": NextContactForm(initial={"next_contact_date": lead.next_contact_date}),
        "deal_amount_form": DealAmountForm(initial={"deal_amount": lead.deal_amount}),
    }


def _apply_parent_list_context(request, context):
    current_url = request.headers.get("HX-Current-URL") or request.get_full_path()
    destination = QueryDict(urlsplit(current_url).query).get("return_to", "")
    parsed = urlsplit(destination)
    if parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return context
    if parsed.path == reverse("board"):
        context.update({"list_url": reverse("board"), "list_label": "← К воронке"})
    elif parsed.path == reverse("calendar"):
        month = QueryDict(parsed.query).get("month", "")
        try:
            year, number = (int(part) for part in month.split("-", 1))
            date(year, number, 1)
        except (ValueError, TypeError):
            month = ""
        context.update({"list_url": f"{reverse('calendar')}?month={month}" if month else reverse("calendar"), "list_label": "← К календарю"})
    elif parsed.path == reverse("inbox"):
        filters = _filter_values(QueryDict(parsed.query))
        context.update({"list_url": _list_url(filters, page=_page_value(QueryDict(parsed.query))), "list_label": "← К заявкам"})
    return context


@login_required
@require_GET
def inbox(request):
    filters = _filter_values(request.GET)
    leads = _base_queryset()
    if filters["tag"]:
        leads = leads.filter(tags__id=int(filters["tag"]))
    if filters["source"]:
        leads = leads.filter(source=filters["source"])
    if filters["status"]:
        leads = leads.filter(status=filters["status"])
    if filters["q"]:
        leads = leads.filter(
            Q(name__icontains=filters["q"])
            | Q(contact_value__icontains=filters["q"])
            | Q(request__icontains=filters["q"])
        )
    leads = leads.distinct()
    counts = Lead.objects.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status=Lead.Status.NEW)),
        in_progress=Count("id", filter=Q(status=Lead.Status.IN_PROGRESS)),
        closed=Count("id", filter=Q(status=Lead.Status.CLOSED)),
    )
    page_obj = Paginator(leads, 30).get_page(request.GET.get("page"))
    for lead in page_obj.object_list:
        lead.open_url = _list_url(filters, page=page_obj.number, selected=lead.pk)
    active_filters = []
    if filters["q"]:
        active_filters.append({"label": f"Поиск: {filters['q']}", "url": _list_url({**filters, "q": ""})})
    if filters["tag"]:
        active_tag = Tag.objects.filter(pk=filters["tag"]).first()
        if active_tag:
            active_filters.append({"label": f"Тег: {active_tag.name}", "url": _list_url({**filters, "tag": ""})})
    if filters["source"]:
        source_label = dict(Lead.Source.choices)[filters["source"]]
        active_filters.append({"label": f"Источник: {source_label}", "url": _list_url({**filters, "source": ""})})
    if filters["status"]:
        status_label = dict(Lead.Status.choices)[filters["status"]]
        active_filters.append({"label": f"Статус: {status_label}", "url": _list_url({**filters, "status": ""})})
    all_tags = list(Tag.objects.all())
    tag_filter_urls = {tag.pk: _list_url({**filters, "tag": str(tag.pk)}) for tag in all_tags}
    for tag in all_tags:
        tag.filter_url = tag_filter_urls[tag.pk]
    status_urls = {value: _list_url({**filters, "status": value}) for value, _ in Lead.Status.choices}
    context = {
        "leads": page_obj,
        "tags": all_tags,
        "tag_filter_urls": tag_filter_urls,
        "counts": counts,
        "source_choices": Lead.Source.choices,
        "status_choices": Lead.Status.choices,
        "selected_tag": filters["tag"],
        "selected_source": filters["source"],
        "selected_status": filters["status"],
        "selected_id": request.GET.get("selected", "") if request.GET.get("selected", "").isdecimal() else "",
        "query": filters["q"],
        "filters": filters,
        "status_urls": status_urls,
        "all_url": reverse("inbox"),
        "active_filters": active_filters,
        "filters_active": bool(active_filters),
        "list_url": _list_url(filters, page=page_obj.number),
        "manual_url": f"{reverse('lead_new')}?{urlencode({'return_to': _list_url(filters, page=page_obj.number)})}",
        "page_urls": {
            number: _list_url(filters, page=number)
            for number in range(1, page_obj.paginator.num_pages + 1)
        },
        "prev_url": _list_url(filters, page=page_obj.previous_page_number()) if page_obj.has_previous() else "",
        "next_url": _list_url(filters, page=page_obj.next_page_number()) if page_obj.has_next() else "",
    }
    selected_id = request.GET.get("selected", "")
    selected_lead = None
    if selected_id.isdecimal() and len(selected_id) <= 12:
        selected_lead = Lead.objects.prefetch_related("tags", "activities").filter(pk=int(selected_id)).first()
    if selected_lead:
        context["selected_lead"] = selected_lead
        context.update(_detail_context(selected_lead, filters=filters, page=page_obj.number, detail_target="#drawer-panel-content"))

    if request.headers.get("HX-Request"):
        if request.headers.get("HX-Target") == "drawer-host":
            if not selected_lead:
                return HttpResponse("")
            return render(request, "crm/partials/lead_drawer.html", context)
        return render(request, "crm/partials/inbox_content.html", context)
    return render(request, "crm/inbox.html", context)


@login_required
@require_GET
def lead_detail(request, lead_id):
    lead = get_object_or_404(_base_queryset(), pk=lead_id)
    return_params = QueryDict(urlsplit(request.GET.get("return_to", "")).query)
    filters = _filter_values(return_params)
    template = "crm/partials/lead_detail.html" if request.headers.get("HX-Request") else "crm/lead_detail_page.html"
    context = _apply_parent_list_context(request, _detail_context(lead, filters=filters, page=_page_value(return_params)))
    return render(request, template, context)


def _safe_return_to_inbox(request, lead_id=None):
    candidate = request.POST.get("return_to", "") or request.GET.get("return_to", "")
    fallback = reverse("lead_detail", args=[lead_id]) if lead_id else reverse("inbox")
    if not candidate or not url_has_allowed_host_and_scheme(candidate, {request.get_host()}, require_https=request.is_secure()):
        return fallback
    parsed = urlsplit(candidate)
    if parsed.path == reverse("inbox"):
        params = QueryDict(parsed.query, mutable=True)
        params.pop("selected", None)
        if lead_id:
            params["selected"] = str(lead_id)
        query = params.urlencode()
        return parsed.path + (f"?{query}" if query else "")
    if parsed.path == reverse("board"):
        return reverse("board")
    if parsed.path == reverse("calendar"):
        month = QueryDict(parsed.query).get("month", "")
        try:
            year, number = (int(part) for part in month.split("-", 1))
            date(year, number, 1)
        except (ValueError, TypeError):
            month = ""
        return f"{reverse('calendar')}?month={month}" if month else reverse("calendar")
    return fallback


@login_required
@require_http_methods(["GET", "POST"])
def lead_new(request):
    return_to = _safe_return_to_inbox(request)
    if request.method == "GET":
        requested_status = request.GET.get("stage", "")
        if requested_status not in Lead.Status.values:
            requested_status = Lead.Status.NEW
        form = LeadForm(initial={"initial_status": requested_status})
        return render(request, "crm/lead_form.html", {"form": form, "is_new": True, "return_to": return_to, "tag_choices": Tag.objects.all()})
    form = LeadForm(request.POST)
    if not form.is_valid():
        return render(request, "crm/lead_form.html", {"form": form, "is_new": True, "return_to": return_to, "tag_choices": Tag.objects.all()}, status=422)
    lead, created = create_lead(
        data=form.cleaned_data,
        submission_id=form.cleaned_data["submission_id"],
        tags=form.cleaned_data.get("tags", []),
        actor=request.user,
    )
    if not created:
        messages.info(request, "Эта заявка уже была сохранена.")
    else:
        set_lead_status(lead=lead, status=form.cleaned_data.get("initial_status") or Lead.Status.NEW, actor=request.user)
        messages.success(request, f"Заявка №{lead.pk} сохранена.")
    return redirect(_safe_return_to_inbox(request, lead.pk))


@login_required
@require_http_methods(["GET", "POST"])
def lead_edit(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    return_to = _safe_return_to_inbox(request, lead.pk)
    if request.method == "GET":
        form = LeadForm(instance=lead)
        return render(request, "crm/lead_form.html", {"form": form, "is_new": False, "lead": lead, "return_to": return_to})
    form = LeadForm(request.POST, instance=lead)
    if not form.is_valid():
        return render(request, "crm/lead_form.html", {"form": form, "is_new": False, "lead": lead, "return_to": return_to}, status=422)
    update_lead(lead=lead, data=form.cleaned_data, actor=request.user)
    messages.success(request, "Изменения сохранены.")
    return redirect(_safe_return_to_inbox(request, lead.pk))


def _detail_target(request):
    return "#drawer-panel-content" if request.headers.get("HX-Target") == "drawer-panel-content" else "#selected-lead"


@login_required
@require_POST
def lead_status(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    try:
        set_lead_status(lead=lead, status=request.POST.get("status", ""), actor=request.user)
    except ValueError as exc:
        notice, notice_kind = str(exc), "error"
    else:
        notice, notice_kind = "Сохранено", "success"
    if request.headers.get("HX-Request"):
        if request.headers.get("HX-Target") == "kanban-board":
            return render(request, "crm/partials/kanban_columns.html", _board_context(action_notice=notice, action_notice_kind=notice_kind))
        current_params = QueryDict(urlsplit(request.headers.get("HX-Current-URL", "")).query)
        filters = _filter_values(current_params)
        context = _detail_context(lead, filters=filters, page=_page_value(current_params), detail_target=_detail_target(request))
        _apply_parent_list_context(request, context)
        context.update({"action_notice": notice, "action_notice_kind": notice_kind})
        return render(request, "crm/partials/lead_detail.html", context)
    messages.error(request, notice) if notice_kind == "error" else messages.success(request, notice)
    return redirect(_safe_return_to_inbox(request, lead.pk))


@login_required
@require_POST
def lead_amount(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    form = DealAmountForm(request.POST)
    if form.is_valid():
        set_deal_amount(lead=lead, value=form.cleaned_data["deal_amount"], actor=request.user)
        notice, notice_kind = "Сумма сделки сохранена", "success"
    else:
        notice, notice_kind = "Укажите сумму от нуля или оставьте поле пустым.", "error"
    lead = Lead.objects.prefetch_related("tags", "activities").get(pk=lead.pk)
    if request.headers.get("HX-Request"):
        current_params = QueryDict(urlsplit(request.headers.get("HX-Current-URL", "")).query)
        context = _detail_context(lead, filters=_filter_values(current_params), page=_page_value(current_params), detail_target=_detail_target(request))
        if not form.is_valid():
            context["deal_amount_form"] = form
        _apply_parent_list_context(request, context)
        context.update({"action_notice": notice, "action_notice_kind": notice_kind})
        return render(request, "crm/partials/lead_detail.html", context)
    messages.error(request, notice) if notice_kind == "error" else messages.success(request, notice)
    return redirect(_safe_return_to_inbox(request, lead.pk))


@login_required
@require_POST
def lead_next_contact(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    form = NextContactForm(request.POST)
    if form.is_valid():
        set_next_contact_date(lead=lead, value=form.cleaned_data["next_contact_date"], actor=request.user)
        notice, notice_kind = "Дата следующего контакта сохранена", "success"
    else:
        notice, notice_kind = "Укажите корректную дату.", "error"
    lead = Lead.objects.prefetch_related("tags", "activities").get(pk=lead.pk)
    if request.headers.get("HX-Request"):
        current_params = QueryDict(urlsplit(request.headers.get("HX-Current-URL", "")).query)
        filters = _filter_values(current_params)
        context = _detail_context(lead, filters=filters, page=_page_value(current_params), detail_target=_detail_target(request))
        if not form.is_valid():
            context["next_contact_form"] = form
        _apply_parent_list_context(request, context)
        context.update({"action_notice": notice, "action_notice_kind": notice_kind})
        return render(request, "crm/partials/lead_detail.html", context)
    messages.error(request, notice) if notice_kind == "error" else messages.success(request, notice)
    return redirect(_safe_return_to_inbox(request, lead.pk))


@login_required
@require_POST
def lead_add_tag(request, lead_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    try:
        _, created = add_lead_tag(lead=lead, value=request.POST.get("tag", ""), actor=request.user)
        notice, notice_kind = ("Тег добавлен" if created else "Тег уже назначен"), "success"
    except ValueError as exc:
        notice, notice_kind = str(exc), "error"
    lead = Lead.objects.prefetch_related("tags", "activities").get(pk=lead.pk)
    if request.headers.get("HX-Request"):
        current_params = QueryDict(urlsplit(request.headers.get("HX-Current-URL", "")).query)
        filters = _filter_values(current_params)
        context = _detail_context(lead, filters=filters, page=_page_value(current_params), detail_target=_detail_target(request))
        _apply_parent_list_context(request, context)
        context.update({"action_notice": notice, "action_notice_kind": notice_kind})
        return render(request, "crm/partials/lead_detail.html", context)
    messages.error(request, notice) if notice_kind == "error" else messages.success(request, notice)
    return redirect(_safe_return_to_inbox(request, lead.pk))


@login_required
@require_POST
def lead_remove_tag(request, lead_id, tag_id):
    lead = get_object_or_404(Lead, pk=lead_id)
    remove_lead_tag(lead=lead, tag_id=tag_id, actor=request.user)
    lead = Lead.objects.prefetch_related("tags", "activities").get(pk=lead.pk)
    if request.headers.get("HX-Request"):
        current_params = QueryDict(urlsplit(request.headers.get("HX-Current-URL", "")).query)
        filters = _filter_values(current_params)
        context = _detail_context(lead, filters=filters, page=_page_value(current_params), detail_target=_detail_target(request))
        _apply_parent_list_context(request, context)
        context.update({"action_notice": "Тег снят", "action_notice_kind": "success"})
        return render(request, "crm/partials/lead_detail.html", context)
    messages.success(request, "Тег снят.")
    return redirect(_safe_return_to_inbox(request, lead.pk))


@login_required
@require_GET
def channels(request):
    candidate = settings.PUBLIC_BASE_URL
    public_address = urlsplit(candidate)
    public_url = candidate if public_address.scheme == "https" and public_address.netloc else ""
    return render(request, "crm/channels.html", {
        "bot_username": settings.BOT_USERNAME,
        "bot_token_present": bool(settings.BOT_TOKEN),
        "public_url": public_url,
        "bot_check_label": "Не проверено",
        "personal_telegram_label": "Не входит в текущий MVP",
    })


@login_required
@require_GET
def board(request):
    context = _board_context()
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "kanban-board":
        return render(request, "crm/partials/kanban_columns.html", context)
    return render(request, "crm/board.html", context)


def _board_context(*, action_notice="", action_notice_kind="success"):
    stats = {
        item["status"]: item
        for item in Lead.objects.values("status").annotate(count=Count("id"), amount_total=Sum("deal_amount"))
    }
    grouped = {status: [] for status, _ in Lead.Status.choices}
    for lead in Lead.objects.prefetch_related("tags").order_by("-created_at", "-id"):
        grouped.setdefault(lead.status, []).append(lead)
    columns = [{
        "value": value,
        "label": label,
        "count": stats.get(value, {}).get("count", 0),
        "amount_total": stats.get(value, {}).get("amount_total") or 0,
        "leads": grouped.get(value, []),
    } for value, label in Lead.Status.choices]
    return {
        "columns": columns,
        "status_choices": Lead.Status.choices,
        "total_count": sum(item["count"] for item in stats.values()),
        "action_notice": action_notice,
        "action_notice_kind": action_notice_kind,
    }


@login_required
@require_GET
def calendar_view(request):
    today = timezone.localdate()
    month_param = request.GET.get("month", "")
    try:
        year, month = (int(part) for part in month_param.split("-", 1))
        month_start = date(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)
    if (month_start - today.replace(day=1)).days > 3660 or (today.replace(day=1) - month_start).days > 3660:
        month_start = today.replace(day=1)
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    previous_month = month_start - timedelta(days=1)
    month_end = next_month - timedelta(days=1)
    events = {}
    scheduled_leads = list(Lead.objects.filter(next_contact_date__range=(month_start, month_end)).prefetch_related("tags").order_by("next_contact_date", "name"))
    for lead in scheduled_leads:
        events.setdefault(lead.next_contact_date, []).append(lead)
    month_names = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
    genitive_month_names = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
    weeks = []
    for week in MonthCalendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month):
        weeks.append([{
            "day": day,
            "in_month": day.month == month_start.month,
            "is_today": day == today,
            "leads": events.get(day, []),
            "accessible_label": f"{day.day} {genitive_month_names[day.month - 1]}: {len(events.get(day, []))} контактов",
        } for day in week])
    context = {
        "weeks": weeks,
        "month_start": month_start,
        "month_label": f"{month_names[month_start.month - 1].capitalize()} {month_start.year}",
        "scheduled_leads": scheduled_leads,
        "previous_month_url": f"?month={previous_month:%Y-%m}",
        "next_month_url": f"?month={next_month:%Y-%m}",
        "today_url": f"?month={today:%Y-%m}",
        "scheduled_count": len(scheduled_leads),
    }
    return render(request, "crm/calendar.html", context)


@login_required
@require_GET
def guide(request):
    return render(request, "crm/guide.html")


@require_GET
def project_doc(request):
    return render(request, "crm/project_doc.html", {
        "bot_username": settings.BOT_USERNAME,
        "status_choices": Lead.Status.choices,
    })


@require_GET
def healthz(request):
    try:
        connection.ensure_connection()
    except Exception:
        return HttpResponse("unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
