"""Visit durations: the category rule table (architecture section 5.2, step 3).

No free source provides visit durations, so this table is **ours**: a default per category, in
minutes, versioned with ``DURATIONS_VERSION``. These are planning assumptions, not facts about the
places. Every generated item stores its duration with ``duration_source = 'category_default'``, and
the user can change any item's duration (``PATCH /v1/items/{id}``), which marks it ``user``.

The keys are the categories the importer stores (``importer/selection.py``): the ``tourism`` value,
an allow-listed ``historic`` value, ``memorial``, and the qualified generic classes with their
``historic_`` prefix (``historic=yes`` is ``historic``). A category not listed gets
``DEFAULT_VISIT_MINUTES``.

To change a value: edit the table, bump ``DURATIONS_VERSION`` (it is part of the planner's
configuration version, stored on every itinerary), and update the golden files.
"""

DURATIONS_VERSION = "2026-11-12.1"

DEFAULT_VISIT_MINUTES = 30

VISIT_MINUTES: dict[str, int] = {
    # tourism=*
    "attraction": 45,
    "museum": 90,
    "gallery": 60,
    "viewpoint": 20,
    "zoo": 150,
    "theme_park": 240,
    "aquarium": 90,
    # historic=* kept by the selection rule (ADR 011)
    "castle": 75,
    "fort": 45,
    "fortress": 60,
    "palace": 75,
    "ruins": 40,
    "archaeological_site": 60,
    "monument": 15,
    "manor": 30,
    "monastery": 45,
    "abbey": 45,
    "church": 30,
    "chapel": 15,
    "temple": 30,
    "city_gate": 15,
    "tower": 30,
    "aqueduct": 20,
    "viaduct": 15,
    "bridge": 15,
    "battlefield": 45,
    "fountain": 15,
    "statue": 10,
    "technical_monument": 30,
    "place_of_worship": 30,
    "cemetery": 40,
    "memorial": 15,
    # generic classes kept only with a name and a notability tag (ADR 011)
    "historic": 30,
    "historic_building": 30,
    "historic_stone": 10,
    "historic_tomb": 15,
    "historic_citywalls": 20,
}


# ADR 026 (proposed lengths): the default length of a restaurant or cafe the user adds. The planner
# never uses it (generated plans have no restaurants); the user can change it per stop.
VENUE_MINUTES: dict[str, int] = {"restaurant": 75, "cafe": 45}


def visit_minutes(category: str | None) -> int:
    """The default visit length for a category; the default for an unknown or missing one."""
    if category is None:
        return DEFAULT_VISIT_MINUTES
    return VISIT_MINUTES.get(category, DEFAULT_VISIT_MINUTES)
