import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError

from apps.accounts.models import AuditEntry
from apps.activities.models import Activity
from apps.leads.models import Contact, PRBriefing, Stage, StageTransition, normalize_domain

from .factories import (
    ActivityFactory,
    CompanyFactory,
    ContactFactory,
    PRBriefingFactory,
    StageFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Domain normalisation (FR-DM-01)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://www.example.com/path?q=1", "example.com"),
        ("http://example.com", "example.com"),
        ("www.example.com", "example.com"),
        ("EXAMPLE.COM", "example.com"),
        ("example.com", "example.com"),
        ("", ""),
        ("  example.com  ", "example.com"),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.django_db
def test_company_save_normalizes_domain():
    company = CompanyFactory(domain="https://www.Acme.COM/about")
    assert company.domain == "acme.com"


# ---------------------------------------------------------------------------
# Company uniqueness (FR-DM-01)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_company_unique_name_domain():
    CompanyFactory(name="Acme", domain="acme.com")
    with pytest.raises(IntegrityError):
        CompanyFactory(name="Acme", domain="acme.com")


@pytest.mark.django_db
def test_company_same_name_different_domain_allowed():
    CompanyFactory(name="Acme", domain="acme.com")
    CompanyFactory(name="Acme", domain="acme.de")  # should not raise


@pytest.mark.django_db
def test_company_str():
    company = CompanyFactory(name="Test Corp")
    assert str(company) == "Test Corp"


# ---------------------------------------------------------------------------
# Stage transitions (FR-PL-02)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_transition_to_creates_stage_transition():
    user = UserFactory()
    stage_a = StageFactory(name_de="Neu", name_en="New")
    stage_b = StageFactory(name_de="Kontaktiert", name_en="Contacted")
    company = CompanyFactory(current_stage=stage_a)

    transition = company.transition_to(stage_b, user, comment="First contact made")

    assert isinstance(transition, StageTransition)
    assert transition.from_stage == stage_a
    assert transition.to_stage == stage_b
    assert transition.by_user == user
    assert transition.comment == "First contact made"
    assert StageTransition.objects.filter(company=company).count() == 1


@pytest.mark.django_db
def test_transition_to_updates_current_stage():
    user = UserFactory()
    stage_a = StageFactory()
    stage_b = StageFactory()
    company = CompanyFactory(current_stage=stage_a)

    company.transition_to(stage_b, user)

    company.refresh_from_db()
    assert company.current_stage == stage_b


@pytest.mark.django_db
def test_multiple_transitions_tracked():
    user = UserFactory()
    stages = [StageFactory() for _ in range(3)]
    company = CompanyFactory(current_stage=stages[0])

    company.transition_to(stages[1], user)
    company.transition_to(stages[2], user)

    assert StageTransition.objects.filter(company=company).count() == 2


# ---------------------------------------------------------------------------
# Archive and reduce (FR-DM-ARCH-01)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_archive_and_reduce_deletes_contacts():
    user = UserFactory()
    company = CompanyFactory()
    ContactFactory(company=company)
    ContactFactory(company=company)

    company.archive_and_reduce("Not a fit", user)

    assert Contact.objects.filter(company=company).count() == 0


@pytest.mark.django_db
def test_archive_and_reduce_keeps_company_fields():
    user = UserFactory()
    company = CompanyFactory(name="Acme", domain="acme.com", location="Berlin", industry="Tech")

    company.archive_and_reduce("Wrong timing", user)
    company.refresh_from_db()

    assert company.name == "Acme"
    assert company.domain == "acme.com"
    assert company.location == "Berlin"
    assert company.industry == "Tech"
    assert company.rejection_reason == "Wrong timing"


@pytest.mark.django_db
def test_archive_and_reduce_clears_prbriefing_qualitative_fields():
    user = UserFactory()
    company = CompanyFactory()
    PRBriefingFactory(
        company=company,
        reality_check="some reality",
        ai_perception="some perception",
        media_hook="a hook",
        story_potential=4,
        fit_score=3,
        priority=PRBriefing.Priority.A,
    )

    company.archive_and_reduce("Disqualified", user)

    briefing = PRBriefing.objects.get(company=company)
    assert briefing.reality_check == ""
    assert briefing.ai_perception == ""
    assert briefing.media_hook == ""
    # scores and priority are kept (they're not qualitative text fields)
    assert briefing.story_potential == 4
    assert briefing.fit_score == 3


@pytest.mark.django_db
def test_archive_and_reduce_anonymises_activities():
    user = UserFactory()
    company = CompanyFactory()
    contact = ContactFactory(company=company)
    ActivityFactory(company=company, contact=contact, note="Detailed call note", performed_by=user)

    company.archive_and_reduce("Archived", user)

    activity = Activity.objects.get(company=company)
    assert activity.note == ""
    assert activity.contact is None
    assert activity.performed_by is None


# ---------------------------------------------------------------------------
# Activity (FR-DM-05)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_activity_links_to_user_and_company():
    user = UserFactory()
    company = CompanyFactory()
    activity = ActivityFactory(company=company, performed_by=user)

    assert activity.company == company
    assert activity.performed_by == user


@pytest.mark.django_db
def test_activity_str():
    activity = ActivityFactory(channel=Activity.Channel.PHONE)
    # __str__ uses get_channel_display() which is translated; check company presence instead
    assert str(activity.company) in str(activity)


# ---------------------------------------------------------------------------
# Groups (FR-US-02)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_default_groups_exist():
    assert Group.objects.filter(name="Admin").exists()
    assert Group.objects.filter(name="PR-Rep").exists()
    assert Group.objects.filter(name="Read-only").exists()


@pytest.mark.django_db
def test_readonly_group_cannot_add_company_in_admin(client):
    """Read-only users must not be able to add companies (FR-US-02)."""
    readonly_group = Group.objects.get(name="Read-only")
    user = UserFactory(is_staff=True)
    user.groups.add(readonly_group)
    user.save()

    client.force_login(user)
    response = client.get("/admin/leads/company/add/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_pr_rep_can_add_company_in_admin(client):
    pr_rep_group = Group.objects.get(name="PR-Rep")
    user = UserFactory(is_staff=True)
    user.groups.add(pr_rep_group)
    user.save()

    client.force_login(user)
    response = client.get("/admin/leads/company/add/")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_audit_entry_log_creates_record():
    user = UserFactory()
    entry = AuditEntry.log(
        action=AuditEntry.Action.STAGE_TRANSITION,
        user=user,
        object_repr="Acme Corp",
        message="Transitioned to Kunde",
    )
    assert entry.pk is not None
    assert AuditEntry.objects.filter(action=AuditEntry.Action.STAGE_TRANSITION).count() == 1


# ---------------------------------------------------------------------------
# Default stages
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_default_stages_created():
    assert Stage.objects.count() == 8
    assert Stage.objects.filter(is_final=True).count() == 1
    assert Stage.objects.filter(name_en="Customer").exists()
    archive_stages = Stage.objects.filter(is_archive=True)
    assert archive_stages.count() == 2
    assert set(archive_stages.values_list("name_en", flat=True)) == {
        "Proposal rejected",
        "Disqualified",
    }
