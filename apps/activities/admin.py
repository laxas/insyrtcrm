from django.contrib import admin

from .models import Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("company", "channel", "direction", "outcome", "occurred_at", "performed_by")
    list_filter = ("channel", "direction", "outcome")
    search_fields = ("company__name", "note")
    autocomplete_fields = ("company", "contact")
    readonly_fields = ("occurred_at",)
    date_hierarchy = "occurred_at"
