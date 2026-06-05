"""Prompt-template tests (FR-PT): model rendering, role-gated config, detail tab."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from apps.leads.models import PromptTemplate
from apps.leads.prompt_variables import build_variable_context, render_prompt

from .factories import (
    CompanyFactory,
    ContactFactory,
    PRBriefingFactory,
    PromptTemplateFactory,
    StageFactory,
    UserFactory,
)


def _prompt_manager(user):
    perm = Permission.objects.get(codename="manage_prompttemplate")
    group, _ = Group.objects.get_or_create(name="Prompt-Manager")
    group.permissions.add(perm)
    user.groups.add(group)
    return user


def auth_client(user):
    c = Client()
    c.force_login(user)
    return c


# ---------------------------------------------------------------------------
# Model + rendering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prompttemplate_str_and_creation():
    t = PromptTemplateFactory(name="Outreach")
    assert str(t) == "Outreach"
    assert PromptTemplate.objects.count() == 1


@pytest.mark.django_db
def test_prompttemplate_name_unique():
    PromptTemplateFactory(name="Dup")
    with pytest.raises(IntegrityError):
        PromptTemplateFactory(name="Dup")


@pytest.mark.django_db
def test_build_variable_context_resolves_company_and_contact():
    company = CompanyFactory(name="Acme", industry="Robotics")
    ContactFactory(company=company, first_name="Jane", full_name="Jane Doe")
    PRBriefingFactory(company=company, priority="A")
    ctx = build_variable_context(company)
    assert ctx["company_name"] == "Acme"
    assert ctx["industry"] == "Robotics"
    assert ctx["contact_first_name"] == "Jane"
    assert ctx["priority"] == "A"


@pytest.mark.django_db
def test_render_fills_known_and_keeps_unknown():
    company = CompanyFactory(name="Acme", industry="Robotics")
    t = PromptTemplateFactory(body="Hi {company_name} ({industry}) — {unknown_var}")
    out = t.render(company)
    assert "Acme" in out
    assert "Robotics" in out
    assert "{unknown_var}" in out  # unknown placeholders are left intact


def test_render_prompt_does_not_crash_on_stray_braces():
    # Pure-function test — no DB needed.
    out = render_prompt("Text with { stray and }{ braces and {company_name}", {"company_name": "X"})
    assert "X" in out


# ---------------------------------------------------------------------------
# Config views — role gated (Prompt-Manager)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prompt_list_requires_login():
    resp = Client().get(reverse("prompt-list"))
    assert resp.status_code == 302
    assert "login" in resp["Location"]


@pytest.mark.django_db
def test_normal_user_cannot_access_prompt_config():
    user = UserFactory()
    resp = auth_client(user).get(reverse("prompt-list"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_prompt_manager_can_access_prompt_config():
    user = _prompt_manager(UserFactory())
    resp = auth_client(user).get(reverse("prompt-list"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_normal_user_cannot_create_prompt():
    user = UserFactory()
    resp = auth_client(user).post(
        reverse("prompt-create"), {"name": "X", "body": "Hi {company_name}", "is_active": "on"}
    )
    assert resp.status_code == 403
    assert PromptTemplate.objects.count() == 0


@pytest.mark.django_db
def test_prompt_manager_can_create_prompt():
    user = _prompt_manager(UserFactory())
    resp = auth_client(user).post(
        reverse("prompt-create"),
        {"name": "Outreach", "description": "", "body": "Hi {company_name}", "is_active": "on"},
    )
    assert resp.status_code == 302
    t = PromptTemplate.objects.get(name="Outreach")
    assert t.created_by == user


@pytest.mark.django_db
def test_prompt_manager_can_edit_and_delete():
    user = _prompt_manager(UserFactory())
    c = auth_client(user)
    t = PromptTemplateFactory(name="Old")
    resp = c.post(
        reverse("prompt-edit", kwargs={"pk": t.pk}),
        {"name": "New", "description": "", "body": "Hi", "is_active": "on"},
    )
    assert resp.status_code == 302
    t.refresh_from_db()
    assert t.name == "New"
    resp = c.post(reverse("prompt-delete", kwargs={"pk": t.pk}))
    assert resp.status_code == 302
    assert PromptTemplate.objects.count() == 0


# ---------------------------------------------------------------------------
# Detail-page Prompt tab — available to any logged-in user
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prompt_tab_renders_selected_template():
    user = UserFactory()
    company = CompanyFactory(name="Acme", industry="Robotics")
    company.current_stage = StageFactory()
    company.save()
    t = PromptTemplateFactory(body="Pitch for {company_name} in {industry}")
    resp = auth_client(user).get(
        reverse("tab-prompt", kwargs={"pk": company.pk}), {"template": t.pk}
    )
    assert resp.status_code == 200
    assert b"Pitch for Acme in Robotics" in resp.content


@pytest.mark.django_db
def test_prompt_tab_inactive_template_not_offered():
    user = UserFactory()
    company = CompanyFactory()
    PromptTemplateFactory(name="Hidden", is_active=False)
    resp = auth_client(user).get(reverse("tab-prompt", kwargs={"pk": company.pk}))
    assert resp.status_code == 200
    assert b"Hidden" not in resp.content
