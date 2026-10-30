from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def rubles(value):
    if value is None or value == "":
        return ""
    amount = Decimal(value)
    formatted = f"{amount:,.2f}" if amount != amount.to_integral_value() else f"{amount:,.0f}"
    return f"{formatted.replace(',', chr(8239)).replace('.', ',')} ₽"
