import uuid

from django import forms

from .models import Lead
from .services import contact_is_valid, normalize_tag


class NextContactForm(forms.Form):
    next_contact_date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date", "aria-describedby": "follow-up-hint"}),
        label="Следующий контакт",
    )


class DealAmountForm(forms.Form):
    deal_amount = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label="Сумма сделки, ₽",
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01", "inputmode": "decimal", "placeholder": "Не указана"}),
    )


class LeadForm(forms.ModelForm):
    submission_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    initial_status = forms.ChoiceField(choices=Lead.Status.choices, required=False, label="Этап воронки", initial=Lead.Status.NEW)
    tags = forms.CharField(
        required=False,
        max_length=200,
        label="Теги",
        widget=forms.TextInput(attrs={"list": "known-tags", "autocomplete": "off", "placeholder": "Например: Сайт, Реклама"}),
        help_text="Выберите подсказку или введите новые теги через запятую. Не больше шести.",
    )

    class Meta:
        model = Lead
        fields = ("name", "contact_type", "contact_value", "request", "deal_amount")
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name", "maxlength": 100}),
            "contact_value": forms.TextInput(attrs={"maxlength": 200}),
            "request": forms.Textarea(attrs={"rows": 5, "maxlength": 3000}),
            "deal_amount": forms.NumberInput(attrs={"min": "0", "step": "0.01", "inputmode": "decimal", "placeholder": "Например, 150000"}),
        }

    def clean_contact_value(self):
        value = self.cleaned_data["contact_value"].strip()
        if not contact_is_valid(self.cleaned_data.get("contact_type", ""), value):
            raise forms.ValidationError("Проверьте адрес или номер для выбранного типа контакта.")
        return value

    def clean_name(self):
        value = self.cleaned_data["name"].strip()
        if not value:
            raise forms.ValidationError("Укажите имя.")
        return value

    def clean_request(self):
        value = self.cleaned_data["request"].strip()
        if len(value) < 5:
            raise forms.ValidationError("Опишите задачу хотя бы в пяти символах.")
        return value

    def clean_tags(self):
        raw = self.cleaned_data["tags"]
        if not raw.strip():
            return []
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if len(parts) > 6:
            raise forms.ValidationError("Можно назначить не больше шести тегов.")
        normalized = set()
        result = []
        for part in parts:
            try:
                name, key = normalize_tag(part)
            except ValueError as exc:
                raise forms.ValidationError(str(exc)) from exc
            if key not in normalized:
                normalized.add(key)
                result.append(name)
        return result
