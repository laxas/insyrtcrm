from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.leads.models import Contact

from .models import Activity


class _BaseActivityForm(forms.ModelForm):
    occurred_at = forms.DateTimeField(
        label=_("Date / time"),
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
    )

    class Meta:
        model = Activity
        fields = ["occurred_at", "contact", "direction", "outcome", "note"]

    def __init__(self, company, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].queryset = Contact.objects.filter(company=company)
        self.fields["contact"].required = False
        self.fields["contact"].empty_label = _("— no contact —")
        if not self.initial.get("occurred_at"):
            now = timezone.localtime(timezone.now())
            self.initial["occurred_at"] = now.strftime("%Y-%m-%dT%H:%M")


class PhoneActivityForm(_BaseActivityForm):
    duration_minutes = forms.IntegerField(
        label=_("Duration (minutes)"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "0"}),
    )

    class Meta(_BaseActivityForm.Meta):
        fields = ["occurred_at", "contact", "direction", "outcome", "duration_minutes", "note"]

    def __init__(self, company, *args, **kwargs):
        super().__init__(company, *args, **kwargs)
        phone_outcomes = [
            Activity.Outcome.NOT_REACHED,
            Activity.Outcome.CALLBACK,
            Activity.Outcome.VOICEMAIL,
            Activity.Outcome.INTERESTED,
            Activity.Outcome.NOT_INTERESTED,
            Activity.Outcome.MEETING,
            Activity.Outcome.OTHER,
        ]
        self.fields["outcome"].choices = [
            (v, label) for v, label in Activity.Outcome.choices if v in phone_outcomes
        ]
        self.fields["outcome"].required = True
        self.fields["direction"].initial = Activity.Direction.OUT

    def save(self, commit=True):
        obj = super().save(commit=False)
        mins = self.cleaned_data.get("duration_minutes")
        obj.duration_seconds = mins * 60 if mins else None
        if commit:
            obj.save()
        return obj


class LinkedInActivityForm(_BaseActivityForm):
    class Meta(_BaseActivityForm.Meta):
        fields = ["occurred_at", "contact", "outcome", "note"]

    def __init__(self, company, *args, **kwargs):
        super().__init__(company, *args, **kwargs)
        li_outcomes = [
            Activity.Outcome.MESSAGE_SENT,
            Activity.Outcome.CONNECTED,
            Activity.Outcome.COMMENT,
            Activity.Outcome.REACTION,
            Activity.Outcome.OTHER,
        ]
        self.fields["outcome"].label = _("Activity type")
        self.fields["outcome"].choices = [
            (v, label) for v, label in Activity.Outcome.choices if v in li_outcomes
        ]
        self.fields["outcome"].required = True
        self.fields.pop("direction", None)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.direction = Activity.Direction.OUT
        if commit:
            obj.save()
        return obj


class EmailActivityForm(_BaseActivityForm):
    subject = forms.CharField(label=_("Subject"), max_length=255, required=False)

    class Meta(_BaseActivityForm.Meta):
        fields = ["occurred_at", "contact", "subject", "direction", "note"]

    def __init__(self, company, *args, **kwargs):
        super().__init__(company, *args, **kwargs)
        self.fields["direction"].initial = Activity.Direction.OUT
        self.fields.pop("outcome", None)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.outcome = Activity.Outcome.SENT
        obj.subject = self.cleaned_data.get("subject", "")
        if commit:
            obj.save()
        return obj


class LetterActivityForm(_BaseActivityForm):
    class Meta(_BaseActivityForm.Meta):
        fields = ["occurred_at", "contact", "note"]

    def __init__(self, company, *args, **kwargs):
        super().__init__(company, *args, **kwargs)
        self.fields.pop("direction", None)
        self.fields.pop("outcome", None)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.direction = Activity.Direction.OUT
        obj.outcome = Activity.Outcome.SENT
        if commit:
            obj.save()
        return obj
