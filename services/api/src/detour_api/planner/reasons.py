"""Reason codes and their fixed templates (CLAUDE.md, hard constraint 1).

Every explanation the planner gives is a code from the tables below, rendered by
``str.format`` with parameters the engine computed. There is no generated text: adding an
explanation means adding a code and its template here. The read endpoints render the stored codes
at read time, so a wording change needs no data migration.
"""

from collections.abc import Mapping

# Why a visit is in the plan (stored in app.itinerary_item.reasons). Parameter-free.
ITEM_TEMPLATES: dict[str, str] = {
    "WIKIDATA_LINKED": "Linked to a Wikidata entry, a sign that it is notable.",
    "WIKIPEDIA_ARTICLE": "Has a Wikipedia article.",
    "WIKIDATA_SITELINKS": "Described in many Wikipedia language editions.",
    "HERITAGE_LISTED": "Listed as heritage in OpenStreetMap.",
    "TAGGED_TOURIST_ATTRACTION": "Mapped as a tourist attraction in OpenStreetMap.",
    "HIGHLIGHT_CATEGORY": "A kind of place ranked high, such as a museum or a castle.",
    "NAMED_SIGHT": "A named sight in the imported map data.",
    "NEAR_CENTRE": "Close to the destination's centre point.",
    "NEAR_PREVIOUS_ITEM": "A short transfer from the previous visit.",
    "ADDS_VARIETY": "Adds a kind of place this plan does not have yet.",
    # Phase 2 seed data.
    "SEED_DATA": "Illustrative seed data, not a planned visit.",
}

# Plan-level notes (stored in app.itinerary.summary and returned with a generation).
NOTE_TEMPLATES: dict[str, str] = {
    "PROFILE_ESSENTIALS": (
        "Essentials: the highest-ranked sights within {radius_km} km, compact days, least travel."
    ),
    "PROFILE_WIDER": (
        "Wider: sights up to {radius_km} km away, more kinds of places, more travel accepted."
    ),
    "DAYS_WITHOUT_VISITS": (
        "Only {candidates} sights could be planned within {radius_km} km; "
        "{empty_days} of {days} days have no visits."
    ),
    "SINGLE_PLAN": (
        "Only one plan is shown: {candidates} sights are available within {radius_km} km, "
        "too few for two clearly different plans (overlap {jaccard_percent} %, "
        "at most {max_percent} % allowed)."
    ),
    "DIVERSITY_ADJUSTED": (
        "To differ from Essentials, Wider gives the sights Essentials already has "
        "{kept_percent} % of their usual weight."
    ),
    "DISTINCT_PLANS": (
        "The two plans share {jaccard_percent} % of their sights (at most {max_percent} % allowed)."
    ),
    "ESTIMATED_TRANSFERS": (
        "{estimated} of {transfers} transfers are estimated from straight-line distance, "
        "not routed."
    ),
    "VISITS_REMOVED_AFTER_ROUTING": (
        "{removed} visits were removed because routed travel times were longer than planned."
    ),
    "NOT_ENOUGH_DISTINCT_PLACES_AFTER_ROUTING": (
        "After routing, the two plans overlapped too much; only one plan is shown."
    ),
    "NO_OPENING_HOURS": (
        "Opening hours are not checked: a place may be closed at the planned time."
    ),
    "NO_MEALS_YET": "Meals are not planned yet; the days leave time free in the evening.",
    "DURATIONS_ARE_DEFAULTS": (
        "Visit lengths are defaults for each kind of place; you can change any of them."
    ),
    "NOTABILITY_FROM_TAGS": (
        "Sights are ranked from OpenStreetMap tags (Wikidata, Wikipedia, heritage, category); "
        "there are no ratings."
    ),
}

# Why no plan can be made (returned with a 422).
ISSUE_TEMPLATES: dict[str, str] = {
    "NO_CANDIDATES": (
        "There are no named sights within {radius_km} km of {destination} in the imported data."
    ),
    "VISITS_LONGER_THAN_DAY": (
        "All {candidates} sights near {destination} take longer than the {day_minutes} minutes "
        "a planned day allows."
    ),
    "NO_IMPORT_RUN": "The region of {destination} has no completed import.",
}


def _render(table: Mapping[str, str], code: str, params: Mapping[str, object]) -> str:
    template = table[code]
    return template.format(**params)


def item_text(code: str) -> str:
    return _render(ITEM_TEMPLATES, code, {})


def note_text(code: str, params: Mapping[str, object]) -> str:
    return _render(NOTE_TEMPLATES, code, params)


def issue_text(code: str, params: Mapping[str, object]) -> str:
    return _render(ISSUE_TEMPLATES, code, params)
