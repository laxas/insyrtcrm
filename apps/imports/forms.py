from django import forms
from django.utils.translation import gettext_lazy as _


class ImportUploadForm(forms.Form):
    file = forms.FileField(
        label=_("File (xlsx or csv)"),
        help_text=_("Upload the Google Sheet export in xlsx or csv format."),
    )
    on_duplicate = forms.ChoiceField(
        label=_("On duplicate"),
        choices=[
            ("skip", _("Skip — keep existing record unchanged")),
            ("update", _("Update — overwrite existing record with new data")),
            ("abort", _("Abort — cancel the entire import if any duplicate is found")),
        ],
        initial="skip",
    )
