"""
Stats query functions — FR-ST-01..06.

All functions return plain Python dicts/lists so they can be JSON-serialised and cached.
Callers are responsible for caching; these functions always hit the DB.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.activities.models import Activity
from apps.leads.models import Company, PRBriefing, Stage, StageTransition

# ---------------------------------------------------------------------------
# FR-ST-01: Pipeline funnel
# ---------------------------------------------------------------------------


def pipeline_funnel() -> list[dict]:
    """Companies per stage, ordered by stage.order. Stageless companies included."""
    stages = Stage.objects.order_by("order")
    stage_counts = {
        row["current_stage_id"]: row["n"]
        for row in Company.objects.values("current_stage_id").annotate(n=Count("id"))
    }
    result = [
        {
            "stage_id": s.pk,
            "name": s.name_de,
            "name_en": s.name_en,
            "count": stage_counts.get(s.pk, 0),
        }
        for s in stages
    ]
    stageless = stage_counts.get(None, 0)
    if stageless:
        result.insert(0, {"stage_id": None, "name": "—", "name_en": "—", "count": stageless})
    return result


# ---------------------------------------------------------------------------
# FR-ST-02: Activities per channel over a date range
# ---------------------------------------------------------------------------


def activities_by_channel(start, end) -> list[dict]:
    """Activity count grouped by channel for the given date range."""
    qs = Activity.objects.filter(occurred_at__date__gte=start, occurred_at__date__lte=end)
    counts = {row["channel"]: row["n"] for row in qs.values("channel").annotate(n=Count("id"))}
    return [
        {"channel": ch.value, "label": str(ch.label), "count": counts.get(ch.value, 0)}
        for ch in Activity.Channel
    ]


# ---------------------------------------------------------------------------
# FR-ST-03: Activities per user and channel
# ---------------------------------------------------------------------------


def activities_by_user_channel(start, end) -> dict:
    """
    Returns {"users": [...], "channels": [...], "matrix": [[count, ...], ...]}
    where matrix[i][j] = count for users[i] and channels[j].
    """
    qs = (
        Activity.objects.filter(occurred_at__date__gte=start, occurred_at__date__lte=end)
        .values("performed_by__username", "performed_by__first_name", "channel")
        .annotate(n=Count("id"))
    )

    channels = [ch.value for ch in Activity.Channel]
    user_map: dict[str, dict[str, int]] = {}
    user_display: dict[str, str] = {}

    for row in qs:
        uname = row["performed_by__username"] or "—"
        fname = row["performed_by__first_name"] or ""
        user_display[uname] = fname or uname
        user_map.setdefault(uname, {})
        user_map[uname][row["channel"]] = row["n"]

    users = sorted(user_map.keys())
    matrix = [[user_map[u].get(ch, 0) for ch in channels] for u in users]
    return {
        "users": [user_display[u] for u in users],
        "channels": channels,
        "matrix": matrix,
    }


# ---------------------------------------------------------------------------
# FR-ST-04: Aging report
# ---------------------------------------------------------------------------


def aging_report(threshold_days: int = 30) -> list[dict]:
    """
    Companies that have been in their current stage for longer than threshold_days.
    Sorted by days_in_stage descending.
    """
    cutoff = timezone.now() - timedelta(days=threshold_days)
    now = timezone.now()

    from django.db.models import OuterRef, Subquery

    latest_transition_at = Subquery(
        StageTransition.objects.filter(company=OuterRef("pk"))
        .order_by("-transitioned_at")
        .values("transitioned_at")[:1]
    )

    qs = (
        Company.objects.filter(current_stage__isnull=False)
        .select_related("current_stage")
        .annotate(entered_at=latest_transition_at)
        .filter(Q(entered_at__lt=cutoff) | Q(entered_at__isnull=True))
        .order_by("entered_at")
    )

    result = []
    for company in qs:
        if company.entered_at:
            days = (now - company.entered_at).days
        else:
            days = (now - company.created_at).days
        result.append(
            {
                "pk": company.pk,
                "name": company.name,
                "stage": company.current_stage.name_de,
                "days_in_stage": days,
            }
        )
    return sorted(result, key=lambda x: x["days_in_stage"], reverse=True)


# ---------------------------------------------------------------------------
# FR-ST-05: Stage dwell times and conversion rates
# ---------------------------------------------------------------------------


def stage_dwell_times() -> list[dict]:
    """
    Average days a company spent in each stage before transitioning out.
    Computed in Python over the full StageTransition history (fast for ≤2000 companies).
    """
    transitions = list(
        StageTransition.objects.filter(from_stage__isnull=False)
        .select_related("from_stage")
        .order_by("company_id", "transitioned_at")
        .values(
            "company_id",
            "from_stage_id",
            "from_stage__name_de",
            "from_stage__order",
            "transitioned_at",
        )
    )

    dwell_days: dict[int, list[float]] = defaultdict(list)
    stage_meta: dict[int, dict] = {}
    prev: dict | None = None

    for tr in transitions:
        sid = tr["from_stage_id"]
        stage_meta[sid] = {
            "name": tr["from_stage__name_de"],
            "order": tr["from_stage__order"],
        }
        if prev and prev["company_id"] == tr["company_id"]:
            delta = tr["transitioned_at"] - prev["transitioned_at"]
            dwell_days[prev["from_stage_id"]].append(delta.total_seconds() / 86400)
        prev = tr

    result = []
    for sid, days in dwell_days.items():
        result.append(
            {
                "stage": stage_meta[sid]["name"],
                "avg_days": round(sum(days) / len(days), 1),
                "transitions": len(days),
                "order": stage_meta[sid]["order"],
            }
        )
    result.sort(key=lambda x: x["order"])
    return result


# ---------------------------------------------------------------------------
# FR-ST-06: Priority / fit distribution
# ---------------------------------------------------------------------------


def priority_fit_distribution() -> dict:
    """
    Returns {"labels": [1,2,3,4,5], "datasets": [{"priority": "A", "data": [n,n,n,n,n]}, ...]}
    """
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in PRBriefing.objects.values("priority", "fit_score").annotate(n=Count("id")):
        if row["priority"] and row["fit_score"]:
            counts[row["priority"]][row["fit_score"]] += row["n"]

    priorities = [p.value for p in PRBriefing.Priority]
    datasets = [
        {"priority": p, "data": [counts[p].get(score, 0) for score in range(1, 6)]}
        for p in priorities
    ]
    return {"labels": list(range(1, 6)), "datasets": datasets}


# ---------------------------------------------------------------------------
# Helper: resolve date range from GET params
# ---------------------------------------------------------------------------

DEFAULT_DAYS = 30


def resolve_date_range(params: dict) -> tuple:
    """
    Return (start_date, end_date, days) from GET params.
    Supports ?days=7|30|90 and ?start=YYYY-MM-DD&end=YYYY-MM-DD.
    """
    from datetime import date

    today = timezone.localdate()

    if params.get("start") and params.get("end"):
        try:
            start = date.fromisoformat(params["start"])
            end = date.fromisoformat(params["end"])
            days = (end - start).days
            return start, end, days
        except ValueError:
            pass

    try:
        days = int(params.get("days", DEFAULT_DAYS))
        if days not in (7, 30, 90):
            days = DEFAULT_DAYS
    except ValueError, TypeError:
        days = DEFAULT_DAYS

    return today - timedelta(days=days), today, days
