"""Django-Q2 task for daily stats cache warm-up."""

from __future__ import annotations

import logging

from django.core.cache import cache

log = logging.getLogger(__name__)

CACHE_TTL = 26 * 3600  # 26 h — survives one missed daily run


def warm_stats_cache() -> None:
    """Pre-compute and cache all stats for the standard date ranges."""
    from datetime import timedelta

    from django.utils import timezone

    from .queries import (
        activities_by_channel,
        activities_by_user_channel,
        aging_report,
        pipeline_funnel,
        priority_fit_distribution,
        stage_dwell_times,
    )

    today = timezone.localdate()
    log.info("Warming stats cache…")

    # FR-ST-01 — pipeline funnel (no date range)
    cache.set("stats:funnel", pipeline_funnel(), CACHE_TTL)

    # FR-ST-05 — dwell times (no date range)
    cache.set("stats:dwell", stage_dwell_times(), CACHE_TTL)

    # FR-ST-06 — priority/fit (no date range)
    cache.set("stats:priority_fit", priority_fit_distribution(), CACHE_TTL)

    # FR-ST-04 — aging (threshold 30 days, the most common query)
    cache.set("stats:aging:30", aging_report(30), CACHE_TTL)

    # FR-ST-02 + FR-ST-03 — activities for standard windows
    for days in (7, 30, 90):
        start = today - timedelta(days=days)
        end = today
        cache.set(f"stats:by_channel:{days}", activities_by_channel(start, end), CACHE_TTL)
        cache.set(
            f"stats:by_user_channel:{days}",
            activities_by_user_channel(start, end),
            CACHE_TTL,
        )

    log.info("Stats cache warm-up complete.")
