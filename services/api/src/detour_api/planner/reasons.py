"""Reason codes and their fixed templates (CLAUDE.md, hard constraint 1).

Every explanation the planner gives is a code from the tables below, rendered by
``str.format`` with parameters the engine computed. There is no generated text: adding an
explanation means adding a code and its template here. The read endpoints render the stored codes
at read time, so a wording change needs no data migration.
"""

from collections.abc import Mapping

# Why a visit is in the plan (stored in app.itinerary_item.reasons). Parameter-free. The meal and
# cuisine reasons of plans made before ADR 026 are retired: a stored code that is not here is not
# shown (repo/itineraries.render_reason).
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
        "{removed} visits were left out so that each day, with its free time and travel times, "
        "fits its hours."
    ),
    "NOT_ENOUGH_DISTINCT_PLACES_AFTER_ROUTING": (
        "After routing, the two plans overlapped too much; only one plan is shown."
    ),
    # Written by planner-1.0.0 and still rendered for its stored itineraries.
    "VISITS_REMOVED_AFTER_ROUTING": (
        "{removed} visits were removed because routed travel times were longer than planned."
    ),
    "NO_OPENING_HOURS": (
        "Opening hours are not checked: a place may be closed at the planned time."
    ),
    "SIGHTS_ONLY": (
        "The plan holds sights only: restaurants and cafes are not planned. Each day keeps free "
        "time around midday; add a place to eat yourself."
    ),
    "BASE_CITY": "{name}: {days} days as a base, with {sights} sights within {radius_km} km.",
    "INTER_CITY_TRAVEL": (
        "Day {day}: {minutes} min by car from {from_name} to {to_name} ({label})."
    ),
    "DISTINCT_ALLOCATION": "The two plans divide the days between different base cities.",
    # Multi-city trips (ADR 024).
    "STOPS_CHANGED": "Your cities change; the trip becomes {name}.",
    # Optimize a hand-made trip (ADR 029).
    "OPTIMIZED": (
        "A shorter order: {saved} min less travel ({before} min before, {after} min after), "
        "about {km} km less."
    ),
    "OPTIMIZE_ESTIMATED": (
        "{estimated} of the {legs} travel times here are estimates from the straight-line "
        "distance, not routed."
    ),
    "OPTIMIZE_NOT_SHORTEST": "A shorter order, not necessarily the shortest.",
    "OPTIMIZE_NO_HOURS": "Opening hours are not known; a place may be closed on its new day.",
    "OPTIMIZE_KEPT": "{count} stops stay exactly where they are (locked, or kept by you).",
    "OPTIMIZE_FAR_KEPT": "{count} stops far from {name} keep their day.",
    "OPTIMIZE_UNDONE": "The order from before Optimize is restored.",
    "OPTIMIZE_LONG_WALKS": (
        "Without a car every leg is a walk: {count} of them are over {km} km. Add a transport leg "
        "for how you will travel."
    ),
    "STOP_REMOVED_ITEMS": "These leave the plan with their days: {items}.",
    "ARRIVAL_TIME_UNKNOWN": (
        "Day {day} starts in {to_name}; the journey from {from_name} is not included in the "
        "day's times (add how you travel as a transport leg)."
    ),
    "STOP_TOO_SMALL_TO_VARY": (
        "{name} has few sights to choose from, so the two plans share most of them there."
    ),
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
        "for visits once its free time is kept."
    ),
    "DAY_FULL_OF_FIXED_ITEMS": (
        "Day {day}: {name} ({minutes} min) does not fit around the items that cannot move "
        "({items}), even with every other visit of the day left out."
    ),
    "DAY_TOO_SHORT_FOR_ADDITION": (
        "Day {day}: {name} ({minutes} min) does not fit with the day's free time, even with every "
        "other visit of the day left out."
    ),
    "NO_TOWN_NEAR_ADDITION": (
        "{name} is {km} km from the plan's base cities, and no town lies within {radius_km} km "
        "of it to be based in."
    ),
    "DAY_NOT_NEAR_ADDITION": (
        "Day {day} cannot take {name}: the day is planned from a base city too far from it, and "
        "it is not a day that could be based near it."
    ),
    "NO_DAY_FOR_NEW_BASE": (
        "{name} is {km} km from the plan's base cities and needs a day based near it, but every "
        "base city has only one day ({bases}); taking one would remove a city from the plan."
    ),
    "SINGLE_CITY_ONLY": (
        "{name} is {km} km from the plan's city; trips here are planned in one city for now "
        "(travel between cities is mostly by rail, which the planner does not model)."
    ),
    "LOCKED_ON_DROPPED_DAY": (
        "Day {day} would be dropped but has locked items ({items}); unlock them or keep the day."
    ),
    "OUTSIDE_STOPS": (
        "{name} is {km} km from your stops; add its town as a stop first, then add {name}."
    ),
    "DAY_HAS_FIXED_ITEMS": (
        "Day {day} cannot be based elsewhere: it has locked items or items you added ({items})."
    ),
    "DRIVE_LEAVES_NO_TIME": (
        "Day {day}: after the {drive_minutes} min drive to {base}, {name} ({minutes} min) "
        "no longer fits in the day."
    ),
    "TRANSPORT_LEG_DAY": (
        "Day {day} has a transport leg you entered ({items}); recalculation cannot plan around it "
        "yet: choose the day and time yourself."
    ),
    "UNSCHEDULED_ITEMS": (
        "Day {day}: {items} have no time or no place; recalculation needs a time and a place "
        "for every item."
    ),
    "ITEM_LOCKED": "{name} is locked: unlock it before removing it.",
    "NOT_A_VISIT": "{name} is a place to eat; only visits can be removed here.",
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
