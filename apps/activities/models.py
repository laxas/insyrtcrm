from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class Activity(models.Model):
    class Channel(models.TextChoices):
        LETTER = "LETTER", _("Letter / Brief")
        PHONE = "PHONE", _("Phone / Telefon")
        LINKEDIN = "LINKEDIN", _("LinkedIn")
        EMAIL = "EMAIL", _("Email / E-Mail")
        OTHER = "OTHER", _("Other / Sonstige")

    class Direction(models.TextChoices):
        OUT = "OUT", _("Outbound")
        IN = "IN", _("Inbound")

    class Outcome(models.TextChoices):
        NOT_REACHED = "not_reached", _("Not reached / Nicht erreicht")
        CALLBACK = "callback", _("Callback agreed / Rückruf vereinbart")
        VOICEMAIL = "voicemail", _("Voicemail / Mailbox")
        INTERESTED = "interested", _("Interested / Interesse")
        NOT_INTERESTED = "not_interested", _("Not interested / Kein Interesse")
        MEETING = "meeting", _("Meeting scheduled / Termin vereinbart")
        SENT = "sent", _("Sent / Versandt")
        CONNECTED = "connected", _("Connected / Verbunden")
        MESSAGE_SENT = "message_sent", _("Message sent / Nachricht gesendet")
        OTHER = "other", _("Other / Sonstige")

    company = models.ForeignKey(
        "leads.Company",
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name=_("Company"),
    )
    contact = models.ForeignKey(
        "leads.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        verbose_name=_("Contact"),
    )
    channel = models.CharField(_("Channel"), max_length=20, choices=Channel.choices, db_index=True)
    direction = models.CharField(_("Direction"), max_length=3, choices=Direction.choices)
    outcome = models.CharField(_("Outcome"), max_length=50, choices=Outcome.choices, blank=True)
    occurred_at = models.DateTimeField(_("Occurred at"), db_index=True)
    performed_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        verbose_name=_("Performed by"),
    )
    duration_seconds = models.PositiveIntegerField(_("Duration (seconds)"), null=True, blank=True)
    note = models.TextField(_("Note"), blank=True)

    class Meta:
        verbose_name = _("Activity")
        verbose_name_plural = _("Activities")
        ordering = ["-occurred_at"]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} — {self.company} — {self.occurred_at:%Y-%m-%d}"
