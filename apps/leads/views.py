from __future__ import annotations

import io
from datetime import timedelta

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
from apps.leads.forms import LeadFilterForm, StageTransitionForm
from apps.leads.models import Company, Stage

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

ALL_COLUMNS: list[dict] = [
    {"key": "name", "label": _("Company"), "sortable": True},
    {"key": "domain", "label": _("Domain"), "sortable": True},
    {"key": "stage", "label": _("Stage"), "sortable": False},
    {"key": "priority", "label": _("Priority"), "sortable": True},
    {"key": "fit", "label": _("Fit"), "sortable": True},
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
# CSV export
# ---------------------------------------------------------------------------


@login_required
def csv_export_view(request):
    import csv

    qs = _build_queryset(request.GET)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="leads.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Firma",
            "Domain",
            "Stage",
            "Priorität",
            "Fit",
            "Branche",
            "Größe",
            "Standort",
            "Owner",
            "Letzte Aktivität",
        ]
    )
    for c in qs:
        br = getattr(c, "prbriefing", None)
        writer.writerow(
            [
                c.name,
                c.domain,
                c.current_stage.name_de if c.current_stage else "",
                br.priority if br else "",
                br.fit_score if br else "",
                c.industry,
                c.size,
                c.city or c.location,
                c.owner.get_full_name() or c.owner.username if c.owner else "",
                c.last_activity_at.strftime("%Y-%m-%d")
                if getattr(c, "last_activity_at", None)
                else "",
            ]
        )
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
