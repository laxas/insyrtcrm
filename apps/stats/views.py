from __future__ import annotations

import csv
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from .queries import (
    activities_by_channel,
    activities_by_user_channel,
    aging_report,
    pipeline_funnel,
    priority_fit_distribution,
    resolve_date_range,
    stage_dwell_times,
)

AGING_THRESHOLD_DEFAULT = 30


@login_required
def dashboard(request):
    start, end, days = resolve_date_range(request.GET)

    try:
        aging_threshold = int(request.GET.get("aging_days", AGING_THRESHOLD_DEFAULT))
        if aging_threshold < 1:
            aging_threshold = AGING_THRESHOLD_DEFAULT
    except ValueError, TypeError:
        aging_threshold = AGING_THRESHOLD_DEFAULT

    # Compute (or serve from cache for standard windows).
    # _get falls back to calling fn() if the cache is unavailable or the key
    # is None (non-cacheable custom windows).
    from django.core.cache import cache

    def _get(key, fn):
        if key is not None:
            try:
                result = cache.get(key)
                if result is not None:
                    return result
            except Exception:
                pass
        return fn()

    if days in (7, 30, 90) and not request.GET.get("start"):
        funnel = _get("stats:funnel", pipeline_funnel)
        dwell = _get("stats:dwell", stage_dwell_times)
        pf = _get("stats:priority_fit", priority_fit_distribution)
        by_channel = _get(f"stats:by_channel:{days}", lambda: activities_by_channel(start, end))
        by_user = _get(
            f"stats:by_user_channel:{days}",
            lambda: activities_by_user_channel(start, end),
        )
        aging = _get(f"stats:aging:{aging_threshold}", lambda: aging_report(aging_threshold))
    else:
        funnel = pipeline_funnel()
        dwell = stage_dwell_times()
        pf = priority_fit_distribution()
        by_channel = activities_by_channel(start, end)
        by_user = activities_by_user_channel(start, end)
        aging = aging_report(aging_threshold)

    ctx = {
        "start": start,
        "end": end,
        "days": days,
        "aging_threshold": aging_threshold,
        # JSON for Chart.js
        "funnel_json": json.dumps(funnel),
        "by_channel_json": json.dumps(by_channel),
        "by_user_json": json.dumps(by_user),
        "dwell_json": json.dumps(dwell),
        "pf_json": json.dumps(pf),
        # Table data
        "aging": aging,
        "dwell": dwell,
    }
    return render(request, "stats/dashboard.html", ctx)


@login_required
def export_csv(request):
    report = request.GET.get("report", "funnel")
    start, end, _days = resolve_date_range(request.GET)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="stats_{report}.csv"'
    writer = csv.writer(response)

    if report == "funnel":
        writer.writerow([_("Stage"), _("Count")])
        for row in pipeline_funnel():
            writer.writerow([row["name"], row["count"]])

    elif report == "by_channel":
        writer.writerow([_("Channel"), _("Count")])
        for row in activities_by_channel(start, end):
            writer.writerow([row["label"], row["count"]])

    elif report == "by_user":
        data = activities_by_user_channel(start, end)
        writer.writerow([_("User")] + data["channels"])
        for i, user in enumerate(data["users"]):
            writer.writerow([user] + data["matrix"][i])

    elif report == "aging":
        try:
            threshold = int(request.GET.get("aging_days", AGING_THRESHOLD_DEFAULT))
        except ValueError, TypeError:
            threshold = AGING_THRESHOLD_DEFAULT
        writer.writerow([_("Company"), _("Stage"), _("Days in stage")])
        for row in aging_report(threshold):
            writer.writerow([row["name"], row["stage"], row["days_in_stage"]])

    elif report == "dwell":
        writer.writerow([_("Stage"), _("Avg days"), _("Transitions")])
        for row in stage_dwell_times():
            writer.writerow([row["stage"], row["avg_days"], row["transitions"]])

    elif report == "priority_fit":
        data = priority_fit_distribution()
        writer.writerow([_("Priority"), "Fit 1", "Fit 2", "Fit 3", "Fit 4", "Fit 5"])
        for ds in data["datasets"]:
            writer.writerow([ds["priority"]] + ds["data"])

    return response
