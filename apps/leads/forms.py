from django import forms
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from apps.leads.models import Company, PRBriefing, Stage


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
    story_potential = forms.ChoiceField(
        label=_("PR story potential"),
        choices=[("", _("All"))] + [(i, str(i)) for i in range(1, 6)],
        required=False,
    )
    ai_profile_clarity = forms.ChoiceField(
        label=_("AI profile (H/M/G)"),
        choices=[("", _("All")), *PRBriefing.AIProfileClarity.choices],
        required=False,
    )
    has_response = forms.ChoiceField(
        label=_("Response received"),
        choices=[("", _("All")), ("yes", _("Yes")), ("no", _("No"))],
        required=False,
    )
    industry = forms.CharField(label=_("Industry"), required=False)
    owner = forms.ModelChoiceField(
        label=_("Owner"),
        queryset=User.objects.filter(is_active=True),
        required=False,
        empty_label=_("All"),
    )
    contacted_by = forms.ModelChoiceField(
        label=_("Contacted by"),
        queryset=User.objects.filter(is_active=True),
        required=False,
        empty_label=_("Anyone"),
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


class LeadCreateForm(forms.ModelForm):
    """Combined form: Company + optional first contact + basic PR briefing."""

    # First contact person (all optional)
    contact_salutation = forms.CharField(label=_("Salutation"), required=False, max_length=50)
    contact_first_name = forms.CharField(label=_("First name"), required=False, max_length=100)
    contact_last_name = forms.CharField(label=_("Last name"), required=False, max_length=100)
    contact_position = forms.CharField(label=_("Position"), required=False, max_length=255)
    contact_email = forms.EmailField(label=_("Email"), required=False)
    contact_phone = forms.CharField(label=_("Phone"), required=False)
    contact_linkedin = forms.URLField(
        label=_("LinkedIn URL"),
        required=False,
        max_length=500,
        widget=forms.URLInput(attrs={"placeholder": "https://linkedin.com/in/…"}),
    )

    # PR briefing basics (all optional)
    priority = forms.ChoiceField(
        label=_("Priority"),
        choices=[("", "—"), *PRBriefing.Priority.choices],
        required=False,
    )
    fit_score = forms.ChoiceField(
        label=_("Fit score"),
        choices=[("", "—")] + [(i, str(i)) for i in range(1, 6)],
        required=False,
    )
    story_potential = forms.ChoiceField(
        label=_("PR story potential"),
        choices=[("", "—")] + [(i, str(i)) for i in range(1, 6)],
        required=False,
    )
    next_step = forms.CharField(
        label=_("Next step"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = Company
        fields = [
            "name",
            "domain",
            "industry",
            "product",
            "size",
            "street",
            "postcode",
            "city",
            "country",
            "investors",
            "b2b_technology",
            "source",
            "owner",
            "current_stage",
        ]
        widgets = {
            "product": forms.Textarea(attrs={"rows": 2}),
            "investors": forms.Textarea(attrs={"rows": 2}),
            "b2b_technology": forms.Textarea(attrs={"rows": 2}),
        }
