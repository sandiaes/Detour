"""Reason codes and their fixed templates (CLAUDE.md, hard constraint 1).

Every explanation the planner gives is a code from the tables below, rendered by
``str.format`` with parameters the engine computed. There is no generated text: adding an
explanation means adding a code and its template here. The read endpoints render the stored codes
at read time, so a wording change needs no data migration.
"""

from collections.abc import Mapping

# Why a visit or a meal is in the plan (stored in app.itinerary_item.reasons). Parameter-free.
ITEM_TEMPLATES: dict[str, str] = {
    # Recalculation (Phase 7, ADR 018). First, so it is the first reason shown.
    "ADDED_BY_YOU": "You added this place: every recalculation keeps it in the plan.",
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
    # Recalculation (Phase 7, ADR 018). Replaced by the next recalculation's notes.
    "PLACE_ADDED": "You added {name} on day {day}; the plan was recalculated around it.",
    "PLACE_REMOVED": "You removed {name}; day {day} was recalculated without it.",
    "PLAN_RESTORED": "You removed {name}, which restores the plan as it was before you added it.",
    "NEW_BASE_DAY": (
        "Day {day} is now based in {name}, {km} km from the nearest other base city, "
        "so that {place} can be visited."
    ),
    "VISITS_MOVED": "{count} visits moved to another day to make room.",
    "VISITS_DROPPED": "{count} visits were left out to make room.",
    "BASE_CITY_DAYS": "{name}: {days} days as a base, with {sights} sights within {radius_km} km.",
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
    # Recalculation (Phase 7, ADR 018): why a place cannot be added or removed.
    "ALREADY_IN_PLAN": "{name} is already in this plan, on day {day}.",
    "ADDITION_LONGER_THAN_DAY": (
        "{name} takes {minutes} min, but a day of this plan has at most {day_minutes} min "
        "for visits once its meals are planned."
    ),
    "DAY_FULL_OF_FIXED_ITEMS": (
        "Day {day}: {name} ({minutes} min) does not fit around the items that cannot move "
        "({items}), even with every other visit of the day left out."
    ),
    "DAY_TOO_SHORT_FOR_ADDITION": (
        "Day {day}: {name} ({minutes} min) does not fit with the day's meals, even with every "
        "other visit of the day left out."
    ),
    "NO_TOWN_NEAR_ADDITION": (
        "{name} is {km} km from the plan's base cities, and no town lies within {radius_km} km "
        "of it to be based in."
    ),
    "NO_DAY_FOR_NEW_BASE": (
        "{name} is {km} km from the plan's base cities and needs a day based near it, but every "
        "base city has only one day ({bases}); taking one would remove a city from the plan."
    ),
    "SINGLE_CITY_ONLY": (
        "{name} is {km} km from the plan's city; trips here are planned in one city for now "
        "(travel between cities is mostly by rail, which the planner does not model)."
    ),
    "DAY_HAS_FIXED_ITEMS": (
        "Day {day} cannot be based elsewhere: it has locked items or items you added ({items})."
    ),
    "DRIVE_LEAVES_NO_TIME": (
        "Day {day}: after the {drive_minutes} min drive to {base}, {name} ({minutes} min) "
        "no longer fits in the day."
    ),
    "UNSCHEDULED_ITEMS": (
        "Day {day}: {items} have no time or no place; recalculation needs a time and a place "
        "for every item."
    ),
    "ITEM_LOCKED": "{name} is locked: unlock it before removing it.",
    "NOT_A_VISIT": "{name} is a meal; only visits can be removed here.",
    "ROUTED_TIMES_TOO_LONG": "With routed travel times, day {day} no longer has room for {name}.",
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
