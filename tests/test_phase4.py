"""Tests for Phase 4: Statistics dashboard (FR-ST-01..06)."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.leads.models import StageTransition

from .factories import (
    ActivityFactory,
    CompanyFactory,
    PRBriefingFactory,
    StageFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user(db):
    return UserFactory(is_active=True)


@pytest.fixture
def auth_client(user):
    from django.test import Client

    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def stage_a(db):
    return StageFactory(name_de="Kontakt", order=1)


@pytest.fixture
def stage_b(db):
    return StageFactory(name_de="Angebot", order=2)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_requires_login():
    from django.test import Client

    c = Client()
    url = reverse("stats:dashboard")
    resp = c.get(url)
    assert resp.status_code == 302
    assert "/login" in resp["Location"]


@pytest.mark.django_db
def test_export_requires_login():
    from django.test import Client

    c = Client()
    url = reverse("stats:export-csv")
    resp = c.get(url)
    assert resp.status_code == 302
    assert "/login" in resp["Location"]


# ---------------------------------------------------------------------------
# FR-ST-01: Pipeline funnel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_funnel_counts_companies_per_stage(stage_a, stage_b):
    CompanyFactory.create_batch(3, current_stage=stage_a)
    CompanyFactory.create_batch(1, current_stage=stage_b)

    from apps.stats.queries import pipeline_funnel

    result = pipeline_funnel()
    names = [r["name"] for r in result]
    assert "Kontakt" in names
    assert "Angebot" in names
    row_a = next(r for r in result if r["name"] == "Kontakt")
    row_b = next(r for r in result if r["name"] == "Angebot")
    assert row_a["count"] == 3
    assert row_b["count"] == 1


@pytest.mark.django_db
def test_funnel_csv_export(auth_client, stage_a):
    CompanyFactory(current_stage=stage_a)
    url = reverse("stats:export-csv") + "?report=funnel"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]
    content = resp.content.decode()
    assert "Kontakt" in content


# ---------------------------------------------------------------------------
# FR-ST-02: Activities by channel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activities_by_channel(user):
    from apps.activities.models import Activity

    now = timezone.now()
    ActivityFactory.create_batch(
        2, channel=Activity.Channel.PHONE, performed_by=user, occurred_at=now
    )
    ActivityFactory(channel=Activity.Channel.EMAIL, performed_by=user, occurred_at=now)

    from apps.stats.queries import activities_by_channel

    today = timezone.localdate()
    result = activities_by_channel(today - timedelta(days=1), today + timedelta(days=1))
    phone = next(r for r in result if r["channel"] == Activity.Channel.PHONE)
    email = next(r for r in result if r["channel"] == Activity.Channel.EMAIL)
    assert phone["count"] == 2
    assert email["count"] == 1


@pytest.mark.django_db
def test_by_channel_csv(auth_client, user):
    from apps.activities.models import Activity

    ActivityFactory(channel=Activity.Channel.PHONE, performed_by=user, occurred_at=timezone.now())
    url = reverse("stats:export-csv") + "?report=by_channel&days=7"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]


# ---------------------------------------------------------------------------
# FR-ST-03: Activities by user and channel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activities_by_user_channel(user):
    from apps.activities.models import Activity

    now = timezone.now()
    ActivityFactory.create_batch(
        3, performed_by=user, channel=Activity.Channel.PHONE, occurred_at=now
    )
    ActivityFactory(performed_by=user, channel=Activity.Channel.EMAIL, occurred_at=now)

    from apps.stats.queries import activities_by_user_channel

    today = timezone.localdate()
    result = activities_by_user_channel(today - timedelta(days=1), today + timedelta(days=1))
    assert user.username in result["users"] or (user.first_name or user.username) in result["users"]
    assert "phone" in result["channels"] or Activity.Channel.PHONE in result["channels"]
    # matrix must be non-empty
    assert len(result["matrix"]) >= 1


@pytest.mark.django_db
def test_by_user_csv(auth_client, user):
    from apps.activities.models import Activity

    ActivityFactory(performed_by=user, channel=Activity.Channel.PHONE, occurred_at=timezone.now())
    url = reverse("stats:export-csv") + "?report=by_user&days=7"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.content.decode())))
    assert len(rows) >= 2  # header + at least one user row


# ---------------------------------------------------------------------------
# FR-ST-04: Aging report
# ---------------------------------------------------------------------------


def _make_transition(company, from_stage, to_stage, days_ago=0):
    """Create a StageTransition and backdate transitioned_at (auto_now_add bypass)."""
    tr = StageTransition.objects.create(company=company, from_stage=from_stage, to_stage=to_stage)
    if days_ago:
        StageTransition.objects.filter(pk=tr.pk).update(
            transitioned_at=timezone.now() - timedelta(days=days_ago)
        )
        tr.refresh_from_db()
    return tr


@pytest.mark.django_db
def test_aging_report_excludes_recent(stage_a, stage_b):
    old_company = CompanyFactory(current_stage=stage_a)
    recent_company = CompanyFactory(current_stage=stage_a)

    _make_transition(old_company, from_stage=stage_b, to_stage=stage_a, days_ago=60)
    _make_transition(recent_company, from_stage=stage_b, to_stage=stage_a, days_ago=5)

    from apps.stats.queries import aging_report

    result = aging_report(threshold_days=30)
    pks = [r["pk"] for r in result]
    assert old_company.pk in pks
    assert recent_company.pk not in pks


@pytest.mark.django_db
def test_aging_report_sorted_descending(stage_a, stage_b):
    c1 = CompanyFactory(current_stage=stage_a)
    c2 = CompanyFactory(current_stage=stage_a)
    _make_transition(c1, from_stage=stage_b, to_stage=stage_a, days_ago=90)
    _make_transition(c2, from_stage=stage_b, to_stage=stage_a, days_ago=45)

    from apps.stats.queries import aging_report

    result = aging_report(30)
    days = [r["days_in_stage"] for r in result]
    assert days == sorted(days, reverse=True)


@pytest.mark.django_db
def test_aging_csv(auth_client, stage_a, stage_b):
    c = CompanyFactory(current_stage=stage_a)
    _make_transition(c, from_stage=stage_b, to_stage=stage_a, days_ago=60)
    url = reverse("stats:export-csv") + "?report=aging&aging_days=30"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert c.name in resp.content.decode()


# ---------------------------------------------------------------------------
# FR-ST-05: Stage dwell times
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_stage_dwell_times(stage_a, stage_b):
    company = CompanyFactory()

    # company went: stage_a → stage_b, then stage_b → stage_a (10 days apart)
    _make_transition(company, from_stage=stage_a, to_stage=stage_b, days_ago=10)
    _make_transition(company, from_stage=stage_b, to_stage=stage_a, days_ago=0)

    from apps.stats.queries import stage_dwell_times

    result = stage_dwell_times()
    stage_names = [r["stage"] for r in result]
    assert "Kontakt" in stage_names


@pytest.mark.django_db
def test_dwell_csv(auth_client, stage_a, stage_b):
    company = CompanyFactory()
    _make_transition(company, from_stage=stage_a, to_stage=stage_b, days_ago=5)
    _make_transition(company, from_stage=stage_b, to_stage=stage_a, days_ago=0)
    url = reverse("stats:export-csv") + "?report=dwell"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]


# ---------------------------------------------------------------------------
# FR-ST-06: Priority / Fit distribution
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_priority_fit_distribution():
    from apps.leads.models import PRBriefing

    PRBriefingFactory(priority=PRBriefing.Priority.A, fit_score=5)
    PRBriefingFactory(priority=PRBriefing.Priority.A, fit_score=5)
    PRBriefingFactory(priority=PRBriefing.Priority.B, fit_score=3)

    from apps.stats.queries import priority_fit_distribution

    result = priority_fit_distribution()
    assert result["labels"] == [1, 2, 3, 4, 5]
    ds_a = next(ds for ds in result["datasets"] if ds["priority"] == "A")
    assert ds_a["data"][4] == 2  # fit_score=5 → index 4
    ds_b = next(ds for ds in result["datasets"] if ds["priority"] == "B")
    assert ds_b["data"][2] == 1  # fit_score=3 → index 2


@pytest.mark.django_db
def test_priority_fit_csv(auth_client):
    from apps.leads.models import PRBriefing

    PRBriefingFactory(priority=PRBriefing.Priority.A, fit_score=4)
    url = reverse("stats:export-csv") + "?report=priority_fit"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]


# ---------------------------------------------------------------------------
# Dashboard view integration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_renders(auth_client):
    url = reverse("stats:dashboard")
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert b"chartFunnel" in resp.content


@pytest.mark.django_db
def test_dashboard_custom_date_range(auth_client):
    url = reverse("stats:dashboard") + "?start=2024-01-01&end=2024-03-31"
    resp = auth_client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_dashboard_invalid_aging_threshold_falls_back(auth_client):
    url = reverse("stats:dashboard") + "?aging_days=notanumber"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert resp.context["aging_threshold"] == 30


@pytest.mark.django_db
def test_unknown_export_report_returns_empty_csv(auth_client):
    url = reverse("stats:export-csv") + "?report=nonexistent"
    resp = auth_client.get(url)
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]
