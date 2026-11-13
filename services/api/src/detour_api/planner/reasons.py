"""Reason codes and their fixed templates (CLAUDE.md, hard constraint 1).

Every explanation the planner gives is a code from the tables below, rendered by
``str.format`` with parameters the engine computed. There is no generated text: adding an
explanation means adding a code and its template here. The read endpoints render the stored codes
at read time, so a wording change needs no data migration.
"""

from collections.abc import Mapping

# Why a visit or a meal is in the plan (stored in app.itinerary_item.reasons). Parameter-free.
ITEM_TEMPLATES: dict[str, str] = {
    "WIKIDATA_LINKED": "Linked to a Wikidata entry, a sign that it is notable.",
    "WIKIPEDIA_ARTICLE": "Has a Wikipedia article.",
    "WIKIDATA_SITELINKS": "Described in many Wikipedia language editions.",
    "HERITAGE_LISTED": "Listed as heritage in OpenStreetMap.",
    "TAGGED_TOURIST_ATTRACTION": "Mapped as a tourist attraction in OpenStreetMap.",
    "HIGHLIGHT_CATEGORY": "A kind of place ranked high, such as a museum or a castle.",
    "NAMED_SIGHT": "A named sight in the imported map data.",
    "NEAR_CENTRE": "Close to the centre of the city the day is planned from.",
    "NEAR_PREVIOUS_ITEM": "A short transfer from the previous visit.",
    "ADDS_VARIETY": "Adds a kind of place this plan does not have yet.",
    # Meals (ADR 016).
    "BREAKFAST_WINDOW": "Breakfast, planned between 07:30 and 10:00.",
    "LUNCH_WINDOW": "Lunch, planned between 12:00 and 14:30.",
    "SNACK_WINDOW": "An afternoon snack, planned between 15:00 and 17:30.",
    "DINNER_WINDOW": "Dinner, planned between 18:30 and 21:00.",
    "VENUE_SUITS_MEAL": "Its venue type in the map data (restaurant or café) suits this meal.",
    "ON_THE_WAY": "Close to the visits before and after it: little detour.",
    "NEAREST_SUITABLE": "The nearest suitable place to eat found in the map data.",
    "NEW_CUISINE": "Adds a cuisine this plan does not have yet.",
    "CUISINE_NOT_SPECIFIED": "Cuisine not specified in the map data.",
    "PLACE_REPEATED": (
        "Already in this plan on an earlier day: no other suitable place to eat is near."
    ),
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
    "VISITS_REMOVED_TO_FIT": (
        "{removed} visits were left out so that each day, with its meals and travel times, "
        "fits its hours."
    ),
    "NOT_ENOUGH_DISTINCT_PLACES_AFTER_ROUTING": (
        "After routing, the two plans overlapped too much; only one plan is shown."
    ),
    # Written by planner-1.0.0 and still rendered for its stored itineraries.
    "VISITS_REMOVED_AFTER_ROUTING": (
        "{removed} visits were removed because routed travel times were longer than planned."
    ),
    "NO_MEALS_YET": "Meals are not planned yet; the days leave time free in the evening.",
    "NO_OPENING_HOURS": (
        "Opening hours are not checked: a place may be closed at the planned time."
    ),
    "MEALS_FROM_MAP_DATA": (
        "Places to eat come from OpenStreetMap: venue type and cuisine only, with no prices, "
        "ratings or opening hours."
    ),
    "MEALS_NOT_PLANNED": (
        "{count} meals are not planned: no suitable place to eat was found within "
        "{radius_km} km of the route in the imported data."
    ),
    "MEALS_SKIPPED_FOR_TRAVEL": (
        "{count} meals fall during travel between base cities and are not planned."
    ),
    "BASE_CITY": "{name}: {days} days as a base, with {sights} sights within {radius_km} km.",
    "INTER_CITY_TRAVEL": (
        "Day {day}: {minutes} min by car from {from_name} to {to_name} ({label})."
    ),
    "DISTINCT_ALLOCATION": "The two plans divide the days between different base cities.",
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
    "NO_BASE_CITIES": (
        "No town in {destination} has at least {min_sights} named sights within {radius_km} km "
        "in the imported data."
    ),
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
