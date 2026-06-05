from __future__ import annotations

import io
from datetime import timedelta

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from apps.accounts.models import DEFAULT_LIST_COLUMNS, UserPreferences
from apps.activities.models import Activity
from apps.leads.forms import (
    LeadCreateForm,
    LeadFilterForm,
    PromptTemplateForm,
    StageTransitionForm,
)
from apps.leads.models import Company, Contact, PRBriefing, PromptTemplate, Stage
from apps.leads.prompt_variables import VARIABLE_GROUPS

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

ALL_COLUMNS: list[dict] = [
    {"key": "name", "label": _("Company"), "sortable": True},
    {"key": "domain", "label": _("Domain"), "sortable": True},
    {"key": "stage", "label": _("Stage"), "sortable": False},
    {"key": "priority", "label": _("Priority"), "sortable": True},
    {"key": "fit", "label": _("Fit"), "sortable": True},
    {"key": "story_potential", "label": _("PR potential"), "sortable": True},
    {"key": "ai_profile", "label": _("AI profile"), "sortable": False},
    {"key": "next_step", "label": _("Next step"), "sortable": False},
    {"key": "industry", "label": _("Industry"), "sortable": True},
    {"key": "owner", "label": _("Owner"), "sortable": False},
    {"key": "size", "label": _("Size"), "sortable": False},
    {"key": "location", "label": _("Location"), "sortable": False},
    {"key": "last_activity", "label": _("Last activity"), "sortable": True},
]

SORT_FIELDS = {
    "name": "name",
    "domain": "domain",
    "priority": "prbriefing__priority",
    "fit": "prbriefing__fit_score",
    "story_potential": "prbriefing__story_potential",
    "industry": "industry",
    "last_activity": "last_activity_at",
}


def _get_prefs(user) -> UserPreferences:
    prefs, _ = UserPreferences.objects.get_or_create(user=user)
    return prefs


def _build_queryset(params: dict):
    """Build annotated, filtered Company queryset from filter params dict."""
    last_activity_at = Subquery(
        Activity.objects.filter(company=OuterRef("pk"))
        .order_by("-occurred_at")
        .values("occurred_at")[:1]
    )
    last_activity_channel = Subquery(
        Activity.objects.filter(company=OuterRef("pk"))
        .order_by("-occurred_at")
        .values("channel")[:1]
    )

    qs = (
        Company.objects.select_related("current_stage", "owner", "prbriefing")
        .prefetch_related("contacts")
        .annotate(
            last_activity_at=last_activity_at,
            last_activity_channel=last_activity_channel,
        )
    )

    q = params.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(domain__icontains=q)
            | Q(contacts__full_name__icontains=q)
            | Q(activities__note__icontains=q)
        ).distinct()

    if stage_id := params.get("stage"):
        qs = qs.filter(current_stage_id=stage_id)

    if priority := params.get("priority"):
        qs = qs.filter(prbriefing__priority=priority)

    if fit := params.get("fit"):
        qs = qs.filter(prbriefing__fit_score=fit)

    if industry := params.get("industry", "").strip():
        qs = qs.filter(industry__icontains=industry)

    if owner_id := params.get("owner"):
        qs = qs.filter(owner_id=owner_id)

    if channel := params.get("channel"):
        qs = qs.filter(last_activity_channel=channel)

    if story := params.get("story_potential"):
        qs = qs.filter(prbriefing__story_potential=story)

    if ai_clarity := params.get("ai_profile_clarity"):
        qs = qs.filter(prbriefing__ai_profile_clarity=ai_clarity)

    has_response = params.get("has_response")
    if has_response == "yes":
        qs = qs.filter(activities__direction=Activity.Direction.IN).distinct()
    elif has_response == "no":
        responded_pks = Company.objects.filter(activities__direction=Activity.Direction.IN).values(
            "pk"
        )
        qs = qs.exclude(pk__in=responded_pks)

    if contacted_by_id := params.get("contacted_by"):
        qs = qs.filter(activities__performed_by_id=contacted_by_id).distinct()

    if days := params.get("days_since_activity"):
        try:
            cutoff = timezone.now() - timedelta(days=int(days))
            qs = qs.filter(Q(last_activity_at__lt=cutoff) | Q(last_activity_at__isnull=True))
        except ValueError, TypeError:
            pass

    sort = params.get("sort", "-last_activity_at")
    db_field = SORT_FIELDS.get(sort.lstrip("-"))
    if db_field:
        qs = qs.order_by(f"-{db_field}" if sort.startswith("-") else db_field)
    else:
        qs = qs.order_by("-last_activity_at")

    return qs


# ---------------------------------------------------------------------------
# Lead list
# ---------------------------------------------------------------------------


class LeadListView(LoginRequiredMixin, ListView):
    model = Company
    template_name = "leads/list.html"
    context_object_name = "companies"
    paginate_by = 50

    def get_queryset(self):
        return _build_queryset(self.request.GET)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = LeadFilterForm(self.request.GET or None)
        prefs = _get_prefs(self.request.user)
        ctx.update(
            {
                "filter_form": form,
                "all_columns": ALL_COLUMNS,
                "active_columns": prefs.get_list_columns(),
                "get_params": self.request.GET.urlencode(),
                "sort": self.request.GET.get("sort", "-last_activity_at"),
            }
        )
        return ctx


# ---------------------------------------------------------------------------
# Lead detail + tab partials
# ---------------------------------------------------------------------------


class LeadDetailView(LoginRequiredMixin, DetailView):
    model = Company
    template_name = "leads/detail.html"
    context_object_name = "company"

    def get_queryset(self):
        return Company.objects.select_related("current_stage", "owner", "prbriefing")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stages"] = Stage.objects.all()
        ctx["transition_form"] = StageTransitionForm()
        ctx["channels"] = Activity.Channel
        ctx["last_activity"] = (
            Activity.objects.filter(company=self.object)
            .select_related("performed_by")
            .order_by("-occurred_at")
            .first()
        )
        return ctx


@login_required
def tab_briefing(request, pk):
    company = get_object_or_404(Company.objects.select_related("prbriefing"), pk=pk)
    return render(request, "leads/partials/tab_briefing.html", {"company": company})


@login_required
def tab_contacts(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return render(
        request,
        "leads/partials/tab_contacts.html",
        {"company": company, "contacts": company.contacts.all()},
    )


@login_required
def tab_activities(request, pk):
    company = get_object_or_404(Company, pk=pk)
    activities = (
        Activity.objects.filter(company=company)
        .select_related("performed_by", "contact")
        .order_by("-occurred_at")
    )
    return render(
        request,
        "leads/partials/tab_activities.html",
        {"company": company, "activities": activities},
    )


@login_required
def tab_prompt(request, pk):
    """Prompt tab: pick an active template, render it against this company (FR-PT)."""
    company = get_object_or_404(
        Company.objects.select_related("current_stage", "owner", "prbriefing"), pk=pk
    )
    templates = PromptTemplate.objects.filter(is_active=True)
    selected = None
    rendered = ""
    template_id = request.GET.get("template")
    if template_id:
        selected = templates.filter(pk=template_id).first()
        if selected:
            rendered = selected.render(company)
    return render(
        request,
        "leads/partials/tab_prompt.html",
        {
            "company": company,
            "templates": templates,
            "selected": selected,
            "rendered": rendered,
            "can_manage_prompts": request.user.has_perm("leads.manage_prompttemplate"),
        },
    )


@login_required
def tab_history(request, pk):
    company = get_object_or_404(Company, pk=pk)
    transitions = company.stage_transitions.select_related(
        "from_stage", "to_stage", "by_user"
    ).order_by("-transitioned_at")
    return render(
        request,
        "leads/partials/tab_history.html",
        {"company": company, "transitions": transitions},
    )


# ---------------------------------------------------------------------------
# Stage transition
# ---------------------------------------------------------------------------


@login_required
def transition_view(request, pk):
    company = get_object_or_404(Company, pk=pk)
    if request.method == "POST":
        form = StageTransitionForm(request.POST)
        if form.is_valid():
            stage = form.cleaned_data["stage"]
            comment = form.cleaned_data["comment"]
            reduce = form.cleaned_data["reduce_data"]
            reason = form.cleaned_data.get("rejection_reason", "")
            with transaction.atomic():
                company.transition_to(stage, request.user, comment=comment)
                if reduce and stage.is_archive:
                    company.archive_and_reduce(reason or comment, request.user)
            messages.success(
                request,
                _("Stage updated to %(stage)s.") % {"stage": stage.name_de},
            )
            return HttpResponseRedirect(reverse("lead-detail", kwargs={"pk": pk}))
    else:
        form = StageTransitionForm()

    return render(
        request,
        "leads/transition_form.html",
        {"company": company, "form": form, "stages": Stage.objects.all()},
    )


# ---------------------------------------------------------------------------
# Column preferences
# ---------------------------------------------------------------------------


@login_required
def save_columns_view(request):
    if request.method == "POST":
        valid_keys = {c["key"] for c in ALL_COLUMNS}
        cols = [c for c in request.POST.getlist("columns") if c in valid_keys]
        prefs = _get_prefs(request.user)
        prefs.list_columns = cols or list(DEFAULT_LIST_COLUMNS)
        prefs.save(update_fields=["list_columns"])
    return HttpResponseRedirect(request.POST.get("next", reverse("lead-list")))


# ---------------------------------------------------------------------------
# Lead create
# ---------------------------------------------------------------------------


@login_required
def lead_create_view(request):
    if request.method == "POST":
        form = LeadCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                company = form.save()
                # Create first contact if any contact field is filled
                first_name = form.cleaned_data.get("contact_first_name", "")
                last_name = form.cleaned_data.get("contact_last_name", "")
                contact_data = {
                    "salutation": form.cleaned_data.get("contact_salutation", ""),
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": f"{first_name} {last_name}".strip(),
                    "position": form.cleaned_data.get("contact_position", ""),
                    "email": form.cleaned_data.get("contact_email", ""),
                    "phone": form.cleaned_data.get("contact_phone", ""),
                    "linkedin_url": form.cleaned_data.get("contact_linkedin", ""),
                }
                if any(v for k, v in contact_data.items() if k != "full_name"):
                    Contact.objects.create(company=company, **contact_data)
                # Create PR briefing if any briefing field is filled
                priority = form.cleaned_data.get("priority", "")
                fit = form.cleaned_data.get("fit_score", "")
                story = form.cleaned_data.get("story_potential", "")
                next_step = form.cleaned_data.get("next_step", "")
                if any([priority, fit, story, next_step]):
                    PRBriefing.objects.create(
                        company=company,
                        priority=priority,
                        fit_score=int(fit) if fit else None,
                        story_potential=int(story) if story else None,
                        next_step=next_step,
                    )
            messages.success(request, _('Lead "%(name)s" created.') % {"name": company.name})
            return HttpResponseRedirect(reverse("lead-detail", kwargs={"pk": company.pk}))
    else:
        form = LeadCreateForm()
    return render(request, "leads/create.html", {"form": form})


# ---------------------------------------------------------------------------
# CSV / XLSX export
# ---------------------------------------------------------------------------


@login_required
def help_view(request):
    return render(request, "help/index.html", {})


def _export_rows(qs):
    """Yield header + data rows for export (shared by CSV and XLSX)."""
    yield [
        "Firma",
        "Domain",
        "Stage",
        "Priorität",
        "Fit",
        "PR-Potenzial",
        "KI-Profil",
        "Nächster Schritt",
        "Branche",
        "Größe",
        "Standort",
        "Source",
        "Owner",
        "Letzte Aktivität",
    ]
    for c in qs:
        br = getattr(c, "prbriefing", None)
        ai_display = ""
        if br and br.ai_profile_clarity:
            ai_display = br.get_ai_profile_clarity_display()
        yield [
            c.name,
            c.domain,
            c.current_stage.name_de if c.current_stage else "",
            br.priority if br else "",
            br.fit_score if br else "",
            br.story_potential if br else "",
            ai_display,
            br.next_step if br else "",
            c.industry,
            c.size,
            c.city or c.location,
            c.source,
            c.owner.get_full_name() or c.owner.username if c.owner else "",
            c.last_activity_at.strftime("%Y-%m-%d") if getattr(c, "last_activity_at", None) else "",
        ]


@login_required
def csv_export_view(request):
    import csv

    qs = _build_queryset(request.GET)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="leads.csv"'
    writer = csv.writer(response)
    for row in _export_rows(qs):
        writer.writerow(row)
    return response


@login_required
def xlsx_export_view(request):
    qs = _build_queryset(request.GET)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"
    for row in _export_rows(qs):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="leads.xlsx"'
    return response


# ---------------------------------------------------------------------------
# Letter export (FR-LT-01 / FR-LT-02)
# ---------------------------------------------------------------------------


@login_required
def letter_export_view(request):
    """POST with company_ids → XLSX download with mail-merge fields."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("lead-list"))

    ids = request.POST.getlist("company_ids")
    if not ids:
        messages.warning(request, _("No leads selected."))
        return HttpResponseRedirect(request.POST.get("next", reverse("lead-list")))

    companies = list(Company.objects.filter(pk__in=ids).prefetch_related("contacts"))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Serienbrief"
    ws.append(
        ["Firma", "Anrede", "Vorname", "Nachname", "Position", "Straße", "PLZ", "Ort", "Land"]
    )
    for company in companies:
        contact = company.contacts.first()
        ws.append(
            [
                company.name,
                contact.salutation if contact else "",
                contact.first_name if contact else "",
                (contact.last_name or contact.full_name) if contact else "",
                contact.position if contact else "",
                company.street,
                company.postcode,
                company.city,
                company.country,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # Stash IDs so the "log letter sent" step can re-use them
    request.session["letter_export_ids"] = [str(i) for i in ids]

    response = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="serienbrief.xlsx"'
    return response


@login_required
def letter_log_view(request):
    """POST — bulk-create 'letter sent' Activity for the last letter export (FR-LT-02)."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("lead-list"))

    ids = request.session.pop("letter_export_ids", [])
    if not ids:
        messages.warning(request, _("No letter export session found. Please export first."))
        return HttpResponseRedirect(reverse("lead-list"))

    companies = Company.objects.filter(pk__in=ids)
    now = timezone.now()
    Activity.objects.bulk_create(
        [
            Activity(
                company=c,
                channel=Activity.Channel.LETTER,
                direction=Activity.Direction.OUT,
                outcome=Activity.Outcome.SENT,
                occurred_at=now,
                performed_by=request.user,
                note="",
            )
            for c in companies
        ]
    )
    messages.success(
        request,
        _("%(n)s letter-sent activities logged.") % {"n": len(ids)},
    )
    return HttpResponseRedirect(reverse("lead-list"))


# ---------------------------------------------------------------------------
# Prompt templates (FR-PT) — configuration is gated to the Prompt-Manager role
# ---------------------------------------------------------------------------


@login_required
@permission_required("leads.manage_prompttemplate", raise_exception=True)
def prompt_template_list(request):
    templates = PromptTemplate.objects.all()
    return render(request, "prompts/list.html", {"templates": templates})


@login_required
@permission_required("leads.manage_prompttemplate", raise_exception=True)
def prompt_template_create(request):
    if request.method == "POST":
        form = PromptTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.save()
            messages.success(
                request, _('Prompt template "%(name)s" created.') % {"name": template.name}
            )
            return HttpResponseRedirect(reverse("prompt-list"))
    else:
        form = PromptTemplateForm()
    return render(
        request,
        "prompts/form.html",
        {"form": form, "variable_groups": VARIABLE_GROUPS, "is_create": True},
    )


@login_required
@permission_required("leads.manage_prompttemplate", raise_exception=True)
def prompt_template_edit(request, pk):
    template = get_object_or_404(PromptTemplate, pk=pk)
    if request.method == "POST":
        form = PromptTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(
                request, _('Prompt template "%(name)s" saved.') % {"name": template.name}
            )
            return HttpResponseRedirect(reverse("prompt-list"))
    else:
        form = PromptTemplateForm(instance=template)
    return render(
        request,
        "prompts/form.html",
        {
            "form": form,
            "variable_groups": VARIABLE_GROUPS,
            "is_create": False,
            "template": template,
        },
    )


@login_required
@permission_required("leads.manage_prompttemplate", raise_exception=True)
def prompt_template_delete(request, pk):
    template = get_object_or_404(PromptTemplate, pk=pk)
    if request.method == "POST":
        name = template.name
        template.delete()
        messages.success(request, _('Prompt template "%(name)s" deleted.') % {"name": name})
        return HttpResponseRedirect(reverse("prompt-list"))
    return render(request, "prompts/confirm_delete.html", {"template": template})
