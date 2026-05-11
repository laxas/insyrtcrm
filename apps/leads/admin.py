from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Company, Contact, PRBriefing, Stage, StageTransition


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ("order", "name_de", "name_en", "is_final", "is_archive")
    list_editable = ("order", "name_de", "name_en", "is_final", "is_archive")
    list_display_links = None
    ordering = ("order",)


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 1
    fields = ("salutation", "first_name", "last_name", "position", "email", "phone", "linkedin_url")


class PRBriefingInline(admin.StackedInline):
    model = PRBriefing
    extra = 0
    can_delete = False
    fieldsets = (
        (
            _("Scores & Priority"),
            {"fields": ("story_potential", "fit_score", "priority", "ai_profile_clarity")},
        ),
        (
            _("Qualitative fields"),
            {
                "fields": (
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
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Dates & Status"),
            {
                "fields": (
                    "last_contact",
                    "research_date",
                    "last_update",
                    "currency_check",
                    "update_needed",
                )
            },
        ),
    )


class StageTransitionInline(admin.TabularInline):
    model = StageTransition
    extra = 0
    readonly_fields = ("from_stage", "to_stage", "transitioned_at", "by_user", "comment")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "domain",
        "current_stage",
        "industry",
        "location",
        "owner",
        "updated_at",
    )
    list_filter = ("current_stage", "industry", "owner")
    search_fields = ("name", "domain", "industry", "location")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("owner",)
    inlines = [ContactInline, PRBriefingInline, StageTransitionInline]
    fieldsets = (
        (None, {"fields": ("name", "domain", "current_stage", "owner")}),
        (
            _("Details"),
            {"fields": ("location", "industry", "product", "size", "investors", "source")},
        ),
        (_("Archive"), {"fields": ("rejection_reason",), "classes": ("collapse",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "position", "email", "phone")
    list_filter = ("company",)
    search_fields = ("full_name", "first_name", "last_name", "email", "company__name")
    autocomplete_fields = ("company",)


@admin.register(PRBriefing)
class PRBriefingAdmin(admin.ModelAdmin):
    list_display = ("company", "priority", "fit_score", "story_potential", "update_needed")
    list_filter = ("priority", "fit_score", "story_potential", "update_needed")
    search_fields = ("company__name",)
    autocomplete_fields = ("company",)


@admin.register(StageTransition)
class StageTransitionAdmin(admin.ModelAdmin):
    list_display = ("company", "from_stage", "to_stage", "transitioned_at", "by_user")
    list_filter = ("to_stage", "from_stage")
    search_fields = ("company__name",)
    readonly_fields = ("company", "from_stage", "to_stage", "transitioned_at", "by_user", "comment")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
