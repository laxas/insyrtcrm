"""
Prompt-template variable registry.

A prompt template stores free text with ``{placeholder}`` markers. The keys of
those markers map to data on a :class:`~apps.leads.models.Company` (and its
primary contact / PR briefing). This module is the single source of truth for

  * which variables exist (used to build the drag-and-drop palette in the editor)
  * how each variable resolves against a concrete company instance.

It deliberately holds no import of the models module so it can be imported from
``models.py`` without creating a circular import — resolvers receive the company
instance as an argument.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

# ``{some_key}`` — only ASCII identifiers are treated as variables.
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


@dataclass(frozen=True)
class PromptVariable:
    """A single insertable variable."""

    key: str
    label: str
    resolver: Callable[[object], str]

    @property
    def token(self) -> str:
        return "{" + self.key + "}"


@dataclass(frozen=True)
class VariableGroup:
    """A labelled group of variables, rendered as one block in the palette."""

    label: str
    variables: list[PromptVariable] = field(default_factory=list)


def _str(value) -> str:
    """Coerce any resolved value to a clean string ("" for missing values)."""
    if value is None:
        return ""
    return str(value)


def _primary_contact(company):
    """First contact of the company, or ``None``."""
    return company.contacts.first()


def _briefing(company):
    """Attached PR briefing, or ``None`` if none exists yet."""
    return getattr(company, "prbriefing", None)


def _company_field(name: str) -> Callable[[object], str]:
    return lambda company: _str(getattr(company, name, ""))


def _contact_field(name: str) -> Callable[[object], str]:
    def resolve(company) -> str:
        contact = _primary_contact(company)
        return _str(getattr(contact, name, "")) if contact else ""

    return resolve


def _briefing_field(name: str) -> Callable[[object], str]:
    def resolve(company) -> str:
        briefing = _briefing(company)
        return _str(getattr(briefing, name, "")) if briefing else ""

    return resolve


def _stage(company) -> str:
    stage = company.current_stage
    return _str(stage.name_de) if stage else ""


def _owner(company) -> str:
    owner = company.owner
    if not owner:
        return ""
    return owner.get_full_name() or owner.username


def _ai_profile_clarity(company) -> str:
    briefing = _briefing(company)
    if briefing and briefing.ai_profile_clarity:
        return _str(briefing.get_ai_profile_clarity_display())
    return ""


# ---------------------------------------------------------------------------
# Registry — order here is the order shown in the editor palette.
# ---------------------------------------------------------------------------

VARIABLE_GROUPS: list[VariableGroup] = [
    VariableGroup(
        label=_("Company"),
        variables=[
            PromptVariable("company_name", _("Company name"), _company_field("name")),
            PromptVariable("domain", _("Domain"), _company_field("domain")),
            PromptVariable("industry", _("Industry / Tech focus"), _company_field("industry")),
            PromptVariable("product", _("Product / Technology"), _company_field("product")),
            PromptVariable("size", _("Company size"), _company_field("size")),
            PromptVariable("investors", _("Investors / Funding"), _company_field("investors")),
            PromptVariable("b2b_technology", _("B2B Technology"), _company_field("b2b_technology")),
            PromptVariable("source", _("Source"), _company_field("source")),
            PromptVariable("location", _("Location"), _company_field("location")),
            PromptVariable("street", _("Street"), _company_field("street")),
            PromptVariable("postcode", _("Postcode"), _company_field("postcode")),
            PromptVariable("city", _("City"), _company_field("city")),
            PromptVariable("country", _("Country"), _company_field("country")),
            PromptVariable("stage", _("Current stage"), _stage),
            PromptVariable("owner", _("Owner"), _owner),
        ],
    ),
    VariableGroup(
        label=_("Primary contact"),
        variables=[
            PromptVariable("contact_salutation", _("Salutation"), _contact_field("salutation")),
            PromptVariable("contact_first_name", _("First name"), _contact_field("first_name")),
            PromptVariable("contact_last_name", _("Last name"), _contact_field("last_name")),
            PromptVariable("contact_full_name", _("Full name"), _contact_field("full_name")),
            PromptVariable("contact_position", _("Position"), _contact_field("position")),
            PromptVariable("contact_email", _("Email"), _contact_field("email")),
            PromptVariable("contact_phone", _("Phone"), _contact_field("phone")),
        ],
    ),
    VariableGroup(
        label=_("PR Briefing"),
        variables=[
            PromptVariable("priority", _("Priority"), _briefing_field("priority")),
            PromptVariable("fit_score", _("Fit score"), _briefing_field("fit_score")),
            PromptVariable(
                "story_potential", _("PR story potential"), _briefing_field("story_potential")
            ),
            PromptVariable("ai_profile_clarity", _("AI profile clarity"), _ai_profile_clarity),
            PromptVariable("reality_check", _("Reality check"), _briefing_field("reality_check")),
            PromptVariable("ai_perception", _("AI perception"), _briefing_field("ai_perception")),
            PromptVariable("media_hook", _("Media hook"), _briefing_field("media_hook")),
            PromptVariable(
                "value_for_decision_makers",
                _("Value for decision makers"),
                _briefing_field("value_for_decision_makers"),
            ),
            PromptVariable(
                "communication_goal", _("Communication goal"), _briefing_field("communication_goal")
            ),
            PromptVariable("trigger_event", _("Trigger event"), _briefing_field("trigger_event")),
            PromptVariable("trigger_type", _("Trigger type"), _briefing_field("trigger_type")),
            PromptVariable(
                "communication_gap", _("Communication gap"), _briefing_field("communication_gap")
            ),
            PromptVariable(
                "innovation_seriousness",
                _("Innovative / Serious"),
                _briefing_field("innovation_seriousness"),
            ),
            PromptVariable("press_news", _("Press / News"), _briefing_field("press_news")),
            PromptVariable("next_step", _("Next step"), _briefing_field("next_step")),
        ],
    ),
]


def _all_variables() -> list[PromptVariable]:
    return [var for group in VARIABLE_GROUPS for var in group.variables]


def build_variable_context(company) -> dict[str, str]:
    """Resolve every known variable against ``company`` into a ``key -> str`` map."""
    return {var.key: var.resolver(company) for var in _all_variables()}


def render_prompt(body: str, context: dict[str, str]) -> str:
    """
    Replace every ``{key}`` in ``body`` with its resolved value.

    Unknown placeholders are left untouched so the author can spot typos, and
    stray/unbalanced braces never raise (unlike ``str.format``).
    """

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key in context:
            return context[key]
        return match.group(0)

    return PLACEHOLDER_RE.sub(replace, body)
