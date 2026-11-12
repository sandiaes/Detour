"""The deterministic planning engine, version 1: attractions and days (Phase 4, ADR 014).

    candidates -> values per profile -> sequencer (heuristic) -> diversity gate
               -> transfers from the travel-time service -> schedule -> independent validator

``engine.generate`` is a pure function of its inputs: the request, the candidate places, the
configuration and the travel times the travel source returns. It reads no clock and uses no
randomness. The database and the network are outside it (``repo/planning.py``,
``planner/travel.py``).
"""
