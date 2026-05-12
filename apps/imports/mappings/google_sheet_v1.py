"""
Column mapping for the Insyrt Google Sheet export — v1 format.

Keys are normalised header strings (stripped, lowercased, emoji removed).
Values are field paths:
  - plain string       → Company field
  - "prbriefing.<x>"  → PRBriefing field
  - "_<special>"      → handled by importer logic (see services.py)

Matching uses startswith so long descriptive headers still hit the right key.
"""

HEADER_MAP: dict[str, str] = {
    "firma": "name",
    "website": "domain",
    "branche": "industry",
    "produkt": "product",
    "standort": "_address",
    "unternehmensgrö": "size",  # handles Unternehmensgröße with ß → oe variation
    "kontaktperson": "_contacts",
    "position": "_contact_position",
    "letzter kontakt": "prbriefing.last_contact",
    "nächster schritt": "prbriefing.next_step",
    "linkedin": "_contact_linkedin",
    "e-mail": "_contact_email",
    "telefon": "_contact_phone",
    "pr-story-potenzial": "prbriefing.story_potential",
    "presse/news": "prbriefing.press_news",
    "ki-wahrnehmung": "prbriefing.ai_perception",
    "ki-profil klar": "prbriefing.ai_profile_clarity",
    "b2b technology": "b2b_technology",
    "investoren": "investors",
    "fit mit insyrt": "prbriefing.fit_score",
    "priorität": "prbriefing.priority",
    "status": "_stage",
    "trigger/anlass": "prbriefing.trigger_event",
    "innovativ": "prbriefing.innovation_seriousness",
    "medien-hook": "prbriefing.media_hook",
    "value für entscheider": "prbriefing.value_for_decision_makers",
    "kommunikationsziel": "prbriefing.communication_goal",
    "recherche-datum": "prbriefing.research_date",
    "letztes update": "prbriefing.last_update",
    "aktualität": "prbriefing.currency_check",
    "update nötig": "prbriefing.update_needed",
    "trigger-typ": "prbriefing.trigger_type",
    "kommunikationslücke": "prbriefing.communication_gap",
    "reality check": "prbriefing.reality_check",
}
