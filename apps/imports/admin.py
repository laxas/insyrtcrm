import contextlib
import hashlib
import os
import tempfile

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from .forms import ImportUploadForm
from .models import ImportBatch
from .services import DuplicateAbortError, LeadImporter


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "source_filename",
        "performed_at",
        "performed_by",
        "rows_created",
        "rows_updated",
        "rows_skipped",
    )
    readonly_fields = (
        "source_filename",
        "performed_at",
        "performed_by",
        "rows_created",
        "rows_updated",
        "rows_skipped",
        "errors_json",
    )
    search_fields = ("source_filename",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="import_upload",
            ),
            path(
                "preview/",
                self.admin_site.admin_view(self.preview_view),
                name="import_preview",
            ),
        ]
        return custom + urls

    # ------------------------------------------------------------------
    # Upload view — show form
    # ------------------------------------------------------------------

    def upload_view(self, request):
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse("admin:index"))

        if request.method == "POST":
            form = ImportUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded = request.FILES["file"]
                on_duplicate = form.cleaned_data["on_duplicate"]

                # Stash file in a temp location so the preview can re-read it
                suffix = ".xlsx" if uploaded.name.endswith(".xlsx") else ".csv"
                fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="insyrt_import_")
                with os.fdopen(fd, "wb") as fh:
                    for chunk in uploaded.chunks():
                        fh.write(chunk)

                # Build a token so the preview form knows which temp file to use
                token = hashlib.sha256(tmp_path.encode()).hexdigest()[:16]
                request.session[f"import_token_{token}"] = {
                    "tmp_path": tmp_path,
                    "filename": uploaded.name,
                    "on_duplicate": on_duplicate,
                }

                return HttpResponseRedirect(reverse("admin:import_preview") + f"?token={token}")
        else:
            form = ImportUploadForm()

        return render(
            request,
            "admin/imports/upload.html",
            {"form": form, "opts": self.model._meta, "title": _("Import Leads")},
        )

    # ------------------------------------------------------------------
    # Preview view — show parsed rows, then commit on confirm
    # ------------------------------------------------------------------

    def preview_view(self, request):
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse("admin:index"))

        # Retrieve session data
        token = request.GET.get("token") or request.POST.get("token", "")
        session_key = f"import_token_{token}"
        session_data = request.session.get(session_key)

        if not session_data:
            messages.error(
                request, _("Import session expired or invalid. Please upload the file again.")
            )
            return HttpResponseRedirect(reverse("admin:import_upload"))

        tmp_path = session_data["tmp_path"]
        filename = session_data["filename"]
        on_duplicate = session_data.get("on_duplicate", "skip")

        if not os.path.exists(tmp_path):
            messages.error(request, _("Uploaded file no longer available. Please upload again."))
            del request.session[session_key]
            return HttpResponseRedirect(reverse("admin:import_upload"))

        # Commit on POST confirm
        if request.method == "POST" and request.POST.get("action") == _("Confirm import"):
            try:
                with open(tmp_path, "rb") as fh:
                    fh.name = filename
                    importer = LeadImporter(fh, on_duplicate=on_duplicate)
                    batch = importer.commit(request.user)
            except DuplicateAbortError as exc:
                messages.error(request, str(exc))
                return HttpResponseRedirect(reverse("admin:import_upload"))
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                del request.session[session_key]

            messages.success(
                request,
                _("Import complete: %(created)s created, %(updated)s updated, %(skipped)s skipped.")
                % {
                    "created": batch.rows_created,
                    "updated": batch.rows_updated,
                    "skipped": batch.rows_skipped,
                },
            )
            return HttpResponseRedirect(reverse("admin:imports_importbatch_changelist"))

        # Preview
        with open(tmp_path, "rb") as fh:
            fh.name = filename
            importer = LeadImporter(fh, on_duplicate=on_duplicate)
            result = importer.preview()

        return render(
            request,
            "admin/imports/preview.html",
            {
                "result": result,
                "token": token,
                "on_duplicate": on_duplicate,
                "opts": self.model._meta,
                "title": _("Import Preview"),
            },
        )
