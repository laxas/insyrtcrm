from django import forms
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from apps.leads.models import PRBriefing, Stage


class LeadFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("Company, domain, contact…")}),
    )
    stage = forms.ModelChoiceField(
        label=_("Stage"),
        queryset=Stage.objects.all(),
        required=False,
        empty_label=_("All stages"),
    )
    priority = forms.ChoiceField(
        label=_("Priority"),
        choices=[("", _("All")), *PRBriefing.Priority.choices],
        required=False,
    )
    fit = forms.ChoiceField(
        label=_("Fit score"),
        choices=[("", _("All"))] + [(i, str(i)) for i in range(1, 6)],
        required=False,
    )
    industry = forms.CharField(label=_("Industry"), required=False)
    owner = forms.ModelChoiceField(
        label=_("Owner"),
        queryset=User.objects.filter(is_active=True),
        required=False,
        empty_label=_("All"),
    )
    channel = forms.ChoiceField(
        label=_("Last activity channel"),
        choices=[("", _("Any channel"))],
        required=False,
    )
    days_since_activity = forms.IntegerField(
        label=_("No contact for (days)"),
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"placeholder": _("e.g. 30")}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.activities.models import Activity

        self.fields["channel"].choices = [("", _("Any channel")), *Activity.Channel.choices]


class StageTransitionForm(forms.Form):
    stage = forms.ModelChoiceField(
        label=_("New stage"),
        queryset=Stage.objects.all(),
        empty_label=None,
    )
    comment = forms.CharField(
        label=_("Comment"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    reduce_data = forms.BooleanField(
        label=_("Reduce personal data (archive)"),
        required=False,
        help_text=_("Deletes contacts, clears qualitative PR-briefing fields and activity notes."),
    )
    rejection_reason = forms.CharField(
        label=_("Rejection reason"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
