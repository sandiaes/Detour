"""The deterministic planning engine, version 2: attractions, meals and days, for a city or an
area (Phase 4, ADR 014; Phase 6, ADR 016).

    scope (base cities of an area) -> candidates -> values per profile -> sequencer (heuristic)
    -> diversity gate -> meals in their windows -> transfers and inter-city legs from the
    travel-time service -> schedule -> independent validator

``engine.generate`` is a pure function of its inputs: the request, the candidate places, the places
to eat, the configuration and the travel times the travel source returns. It reads no clock and
uses no randomness. The database and the network are outside it (``repo/planning.py``,
``planner/travel.py``).
"""
