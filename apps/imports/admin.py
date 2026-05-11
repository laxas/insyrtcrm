from django.contrib import admin

from .models import ImportBatch


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
