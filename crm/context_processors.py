from django.conf import settings
from django.db.models import Count, Q
from django.http import QueryDict
from django.urls import reverse
from urllib.parse import urlsplit

from .models import Lead, Tag


def product_flags(request):
    candidate_public_url = settings.PUBLIC_BASE_URL
    parsed_public_url = urlsplit(candidate_public_url)
    context = {
        "DEMO_MODE": settings.DEMO_MODE,
        "BOT_USERNAME": settings.BOT_USERNAME,
        "PUBLIC_BASE_URL": candidate_public_url if parsed_public_url.scheme == "https" and parsed_public_url.netloc else "",
        "BOT_TOKEN_PRESENT": bool(settings.BOT_TOKEN),
    }
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return context
    params = QueryDict("", mutable=True)
    request_query = request.GET.get("q", "").strip()[:100]
    request_tag = request.GET.get("tag", "")
    if not request_tag.isdecimal() or len(request_tag) > 12 or not Tag.objects.filter(pk=int(request_tag)).exists():
        request_tag = ""
    request_source = request.GET.get("source", "")
    request_status = request.GET.get("status", "")
    if request_source not in Lead.Source.values:
        request_source = ""
    if request_status not in Lead.Status.values:
        request_status = ""
    for key, value in (("q", request_query), ("tag", request_tag), ("source", request_source), ("status", request_status)):
        if value:
            params[key] = value

    def nav_url(**changes):
        nav_params = params.copy()
        for key, value in changes.items():
            if value:
                nav_params[key] = value
            else:
                nav_params.pop(key, None)
        encoded = nav_params.urlencode()
        return reverse("inbox") + (f"?{encoded}" if encoded else "")

    nav_tags = list(Tag.objects.annotate(lead_count=Count("leads")).order_by("-lead_count", "name"))
    for tag in nav_tags:
        tag.filter_url = nav_url(tag=str(tag.pk))
    counts_by_status = dict(Lead.objects.values_list("status").annotate(count=Count("id")))
    nav_statuses = [
        {"value": value, "label": label, "count": counts_by_status.get(value, 0), "filter_url": nav_url(status=value)}
        for value, label in Lead.Status.choices
    ]
    context.update({
        "nav_counts": Lead.objects.aggregate(
            total=Count("id"),
            new=Count("id", filter=Q(status=Lead.Status.NEW)),
            in_progress=Count("id", filter=Q(status=Lead.Status.IN_PROGRESS)),
            closed=Count("id", filter=Q(status=Lead.Status.CLOSED)),
        ),
        "nav_tags": nav_tags,
        "nav_statuses": nav_statuses,
        "nav_all_url": reverse("inbox"),
        "nav_status_urls": {value: nav_url(status=value) for value, _ in Lead.Status.choices},
        "nav_current_status": request_status,
        "nav_current_tag": request_tag,
        "profile_label": "Владелец" if request.user.is_staff else "Проверяющий",
    })
    return context
