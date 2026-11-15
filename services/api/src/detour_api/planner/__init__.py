"""The deterministic planning engine, version 3: sights and days, for a city, an area or a route of
cities (Phase 4, ADR 014; Phase 6, ADR 016; ADR 024; ADR 026 removed the meals).

    scope (base cities of an area) -> candidates -> values per profile -> sequencer (heuristic)
    -> diversity gate -> days with an unplanned midday gap -> transfers and inter-city legs from
    the travel-time service -> schedule -> independent validator

``engine.generate`` is a pure function of its inputs: the request, the candidate places, the
configuration and the travel times the travel source returns. It reads no clock and
uses no randomness. The database and the network are outside it (``repo/planning.py``,
``planner/travel.py``).
"""
