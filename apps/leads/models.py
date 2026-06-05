import re

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


def normalize_domain(raw: str) -> str:
    """Lowercase, strip protocol and www prefix, strip path. Reused by importer."""
    if not raw:
        return ""
    domain = raw.strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0].split("?")[0].split("#")[0]
    return domain


def parse_address(raw: str) -> dict[str, str]:
    """
    Parse a free-text German/Austrian/Swiss address into street/postcode/city/country.

    Handles two common formats from the Google Sheet export:
      "Street, Postcode, City, Country"   e.g. "Kantstraße 127, 10625, Berlin, Deutschland"
      "Street, Postcode City"             e.g. "Jörg-Syrlin-Straße 6, 73079 Süßen"
    """
    empty = {"street": "", "postcode": "", "city": "", "country": ""}
    if not raw or not raw.strip():
        return empty

    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]

    postcode_re = re.compile(r"^(\d{4,5})\s*(.*)")
    for i, part in enumerate(parts):
        m = postcode_re.match(part)
        if m:
            postcode = m.group(1)
            city_in_segment = m.group(2).strip()
            street = ", ".join(parts[:i])
            if city_in_segment:
                city = city_in_segment
                country = parts[i + 1] if i + 1 < len(parts) else ""
            else:
                city = parts[i + 1] if i + 1 < len(parts) else ""
                country = parts[i + 2] if i + 2 < len(parts) else ""
            return {"street": street, "postcode": postcode, "city": city, "country": country}

    return {"street": raw.strip(), "postcode": "", "city": "", "country": ""}


class Stage(models.Model):
    name_de = models.CharField(_("Name (DE)"), max_length=100)
    name_en = models.CharField(_("Name (EN)"), max_length=100)
    order = models.PositiveSmallIntegerField(_("Order"), default=0, db_index=True)
    is_final = models.BooleanField(_("Is final state"), default=False)
    is_archive = models.BooleanField(_("Is archive stage"), default=False)

    class Meta:
        verbose_name = _("Stage")
        verbose_name_plural = _("Stages")
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.name_de} / {self.name_en}"


class Company(models.Model):
    name = models.CharField(_("Company name"), max_length=255, db_index=True)
    domain = models.CharField(_("Domain"), max_length=255, blank=True, db_index=True)
    location = models.CharField(_("Location"), max_length=255, blank=True)
    industry = models.CharField(_("Industry / Tech focus"), max_length=255, blank=True)
    product = models.TextField(_("Product / Technology"), blank=True)
    size = models.TextField(_("Company size"), blank=True)
    investors = models.TextField(_("Investors / Funding"), blank=True)
    b2b_technology = models.TextField(_("B2B Technology"), blank=True)
    source = models.CharField(_("Source"), max_length=255, blank=True)
    # Structured address — parsed from the free-text location field at import time
    street = models.CharField(_("Street"), max_length=255, blank=True)
    postcode = models.CharField(_("Postcode"), max_length=20, blank=True)
    city = models.CharField(_("City"), max_length=255, blank=True)
    country = models.CharField(_("Country"), max_length=100, blank=True)
    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_companies",
        verbose_name=_("Owner"),
    )
    current_stage = models.ForeignKey(
        "Stage",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="companies",
        verbose_name=_("Current stage"),
    )
    rejection_reason = models.TextField(_("Rejection reason"), blank=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        constraints = [
            models.UniqueConstraint(fields=["name", "domain"], name="unique_company_name_domain"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        self.domain = normalize_domain(self.domain)
        super().save(*args, **kwargs)

    def transition_to(self, stage: Stage, user: User, comment: str = "") -> StageTransition:
        """Create a StageTransition record and update current_stage (FR-PL-02)."""
        transition = StageTransition.objects.create(
            company=self,
            from_stage=self.current_stage,
            to_stage=stage,
            by_user=user,
            comment=comment,
        )
        self.current_stage = stage
        self.save(update_fields=["current_stage", "updated_at"])
        return transition

    def archive_and_reduce(self, reason: str, user: User) -> None:
        """
        FR-DM-ARCH-01: minimise personal data when archiving.
        Keeps: name, domain, location, industry, rejection_reason, stage history.
        Deletes: all Contact records.
        Clears: qualitative PR briefing text fields, activity notes/contacts.
        """
        self.contacts.all().delete()
        self.activities.update(note="", contact=None, performed_by=None, duration_seconds=None)
        try:
            b = self.prbriefing
            for field in (
                "reality_check",
                "ai_perception",
                "media_hook",
                "value_for_decision_makers",
                "communication_goal",
                "trigger_event",
                "trigger_type",
                "communication_gap",
                "innovation_seriousness",
                "press_news",
                "next_step",
            ):
                setattr(b, field, "")
            b.save()
        except PRBriefing.DoesNotExist:
            pass
        self.rejection_reason = reason
        self.save(update_fields=["rejection_reason", "updated_at"])


class Contact(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name=_("Company"),
    )
    salutation = models.CharField(_("Salutation"), max_length=50, blank=True)
    first_name = models.CharField(_("First name"), max_length=100, blank=True)
    last_name = models.CharField(_("Last name"), max_length=100, blank=True)
    full_name = models.CharField(_("Full name"), max_length=255, blank=True)
    position = models.CharField(_("Position"), max_length=255, blank=True)
    email = models.EmailField(_("Email"), blank=True)
    phone = models.TextField(_("Phone"), blank=True)
    linkedin_url = models.URLField(_("LinkedIn URL"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("Contact")
        verbose_name_plural = _("Contacts")

    def __str__(self) -> str:
        name = self.full_name or f"{self.first_name} {self.last_name}".strip()
        return name or str(_("(unnamed)"))


class PRBriefing(models.Model):
    class AIProfileClarity(models.TextChoices):
        HIGH = "H", _("High / Hoch")
        MEDIUM = "M", _("Medium / Mittel")
        LOW = "G", _("Low / Gering")

    class Priority(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"

    SCORE_CHOICES = [(i, str(i)) for i in range(1, 6)]

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="prbriefing",
        verbose_name=_("Company"),
    )
    reality_check = models.TextField(_("Reality check"), blank=True)
    ai_perception = models.TextField(_("AI perception"), blank=True)
    ai_profile_clarity = models.CharField(
        _("AI profile clarity"),
        max_length=1,
        choices=AIProfileClarity.choices,
        blank=True,
    )
    media_hook = models.TextField(_("Media hook"), blank=True)
    value_for_decision_makers = models.TextField(_("Value for decision makers"), blank=True)
    communication_goal = models.TextField(_("Communication goal"), blank=True)
    trigger_event = models.TextField(_("Trigger event"), blank=True)
    trigger_type = models.TextField(_("Trigger type"), blank=True)
    communication_gap = models.TextField(_("Communication gap"), blank=True)
    innovation_seriousness = models.TextField(_("Innovative / Serious"), blank=True)
    story_potential = models.PositiveSmallIntegerField(
        _("PR story potential (1-5)"), null=True, blank=True, choices=SCORE_CHOICES
    )
    fit_score = models.PositiveSmallIntegerField(
        _("Fit score (1-5)"), null=True, blank=True, choices=SCORE_CHOICES
    )
    priority = models.CharField(_("Priority"), max_length=1, choices=Priority.choices, blank=True)
    press_news = models.TextField(_("Press / News"), blank=True)
    next_step = models.TextField(_("Next step"), blank=True)
    last_contact = models.DateField(_("Last contact"), null=True, blank=True)
    research_date = models.DateField(_("Research date"), null=True, blank=True)
    last_update = models.DateField(_("Last update"), null=True, blank=True)
    currency_check = models.TextField(_("Currency check (Aktualität)"), blank=True)
    update_needed = models.BooleanField(_("Update needed"), default=False)

    class Meta:
        verbose_name = _("PR Briefing")
        verbose_name_plural = _("PR Briefings")

    def __str__(self) -> str:
        return f"PR Briefing — {self.company}"


class PromptTemplate(models.Model):
    """
    A reusable text template with ``{variable}`` placeholders (FR-PT).

    Configured centrally by users in the *Prompt-Manager* role and then
    available to everyone on the lead detail page, where the placeholders are
    filled from the selected company's data. See ``prompt_variables`` for the
    list of supported variables and how they resolve.
    """

    name = models.CharField(_("Name"), max_length=150, unique=True)
    description = models.CharField(_("Description"), max_length=255, blank=True)
    body = models.TextField(
        _("Template body"),
        help_text=_("Use {variable} placeholders — insert them from the palette."),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        help_text=_("Only active templates can be selected on the lead detail page."),
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prompt_templates",
        verbose_name=_("Created by"),
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Prompt template")
        verbose_name_plural = _("Prompt templates")
        ordering = ["name"]
        permissions = [
            ("manage_prompttemplate", _("Can create and edit prompt templates")),
        ]

    def __str__(self) -> str:
        return self.name

    def render(self, company: Company) -> str:
        """Fill the template's placeholders from ``company``'s data (FR-PT)."""
        from apps.leads.prompt_variables import build_variable_context, render_prompt

        return render_prompt(self.body, build_variable_context(company))


class StageTransition(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="stage_transitions",
        verbose_name=_("Company"),
    )
    from_stage = models.ForeignKey(
        Stage,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("From stage"),
    )
    to_stage = models.ForeignKey(
        Stage,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("To stage"),
    )
    transitioned_at = models.DateTimeField(_("Transitioned at"), auto_now_add=True)
    by_user = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stage_transitions",
        verbose_name=_("By user"),
    )
    comment = models.TextField(_("Comment"), blank=True)

    class Meta:
        verbose_name = _("Stage transition")
        verbose_name_plural = _("Stage transitions")
        ordering = ["-transitioned_at"]

    def __str__(self) -> str:
        return f"{self.company} → {self.to_stage}"
