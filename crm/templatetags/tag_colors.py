import hashlib

from django import template

register = template.Library()


@register.filter
def tag_color(tag):
    """Return a stable palette index so each tag keeps its color everywhere."""
    if getattr(tag, "pk", None):
        return (tag.pk - 1) % 8
    value = getattr(tag, "normalized_name", str(tag)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:2], "big") % 8
