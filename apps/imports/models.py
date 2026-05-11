from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class ImportBatch(models.Model):
    source_filename = models.CharField(_("Source filename"), max_length=255)
    performed_at = models.DateTimeField(_("Performed at"), auto_now_add=True)
    performed_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="import_batches",
        verbose_name=_("Performed by"),
    )
    rows_created = models.PositiveIntegerField(_("Rows created"), default=0)
    rows_updated = models.PositiveIntegerField(_("Rows updated"), default=0)
    rows_skipped = models.PositiveIntegerField(_("Rows skipped"), default=0)
    errors_json = models.JSONField(_("Errors"), default=list)
    notes = models.TextField(_("Notes"), blank=True)

    class Meta:
        verbose_name = _("Import batch")
        verbose_name_plural = _("Import batches")
        ordering = ["-performed_at"]

    def __str__(self) -> str:
        return f"{self.source_filename} ({self.performed_at:%Y-%m-%d %H:%M})"
