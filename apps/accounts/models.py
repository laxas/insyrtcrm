from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

# TODO(phase-1-mfa): add django-otp TOTP MFA once Django 6 support is confirmed.


class AuditEntry(models.Model):
    """FR-US-05: lightweight audit log for security-relevant actions.
    Using a custom model rather than django-auditlog to avoid Django 6 compat risk.
    """

    class Action(models.TextChoices):
        LOGIN = "LOGIN", _("Login")
        LOGOUT = "LOGOUT", _("Logout")
        ROLE_CHANGE = "ROLE_CHANGE", _("Role change")
        DATA_REDUCTION = "DATA_REDUCTION", _("Data reduction")
        IMPORT = "IMPORT", _("Import")
        STAGE_TRANSITION = "STAGE_TRANSITION", _("Stage transition")

    action = models.CharField(_("Action"), max_length=50, choices=Action.choices, db_index=True)
    user = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
        verbose_name=_("User"),
    )
    timestamp = models.DateTimeField(_("Timestamp"), auto_now_add=True, db_index=True)
    object_repr = models.CharField(_("Object"), max_length=255, blank=True)
    message = models.TextField(_("Message"), blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)

    class Meta:
        verbose_name = _("Audit entry")
        verbose_name_plural = _("Audit entries")
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.get_action_display()} — {self.user} — {self.timestamp:%Y-%m-%d %H:%M}"

    @classmethod
    def log(
        cls,
        action: str,
        user: User | None = None,
        object_repr: str = "",
        message: str = "",
        ip_address: str | None = None,
    ) -> AuditEntry:
        return cls.objects.create(
            action=action,
            user=user,
            object_repr=object_repr,
            message=message,
            ip_address=ip_address,
        )
