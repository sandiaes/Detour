# ADR 009 — Region readiness thresholds and enablement order

- **Status:** **Accepted** on 2026-11-12 (owner approval). Closes the open item in D2.
- **Date:** 2026-11-12
- **Related:** [`../spikes/s2-data-findings.md`](../spikes/s2-data-findings.md), [`../kpis.md`](../kpis.md)
  ("Region readiness"), [`003-scope-opening-hours-and-attractions.md`](003-scope-opening-hours-and-attractions.md)

## Context

The KPI "Region readiness" requires 100% of enabled regions to pass minimum data thresholds set
after spike S2. S2 and its rerun measured the five pilot countries. The numbers below are chosen
by judgement from those measurements; none comes from a provider.

## Proposed decision

A region is enabled only if its import report meets every gate:

| # | Gate | Austria | Czechia | Hungary | Italy | Japan |
|---|---|---|---|---|---|---|
| 1 | Restaurants with a name: at least 90% | 98% pass | 94% pass | 94% pass | 91% pass | 95% pass |
| 2 | Restaurants with a cuisine: at least 30% | 54% pass | 36% pass | 35% pass | 38% pass | 49% pass |
| 3 | At least 5,000 restaurants | 26,504 pass | 17,826 pass | 9,160 pass | 118,565 pass | 141,003 pass |
| 4 | At least 5,000 named attractions, at least 40% of attractions named | 13,694 (61%) pass | 22,058 (46%) pass | 8,966 (68%) pass | 57,876 (46%) pass | 30,370 (78%) pass |
| 5 | Names displayable: at least 90% of names have Latin letters, or a display rule is implemented | pass | pass | pass | pass | **fails**: 73% to 79% have none |
| 6 | Sum of enabled regions' `geo` data at most 250 MB (half of Supabase Free's 500 MB) | 9.2 MB | 12.0 MB | 4.1 MB | 42.3 MB | 32.4 MB |

Gate 4 is measured after the stricter memorial test that ADR 003's addendum calls for; the
Czech figure above still contains about 22,800 memorials.

**Order of enablement:** Austria, Czechia and Hungary first; Italy second; Japan last, only
after gate 5 is met by a display rule and the rail question (D4) is settled.

## Alternatives

| Alternative | Why not |
|---|---|
| Enable all five at once | Japan fails gate 5; Italy and Japan add most of the data and request load. |
| Gate on opening-hours coverage | Opening hours are out of scope (ADR 003). |

## Consequences

- With these gates, four of five countries pass today; the size total is 100.0 MB against the
  250 MB gate.
- The import report must compute gates 1 to 6 automatically (Phase 2). **Done in Phase 2**
  (`detour_api/importer/report.py`, ADR 012): exact ratios, no manual override, and an unknown
  value never passes. Gate 5 uses the Latin-letter share because no display rule is implemented.
  Gate 4 and the other figures in the table above come from spike S2 and were measured before the
  ADR 011 rule: the first real import reports the new values.

## Amendment of 2026-11-14 (ADR 026): gates 1 to 3 removed (proposed, not built)

[ADR 026](026-trip-manager-first.md) removes restaurants and cafés from the imported data. Gates 1
(restaurants with a name), 2 (restaurants with a cuisine) and 3 (at least 5,000 restaurants) have
nothing to measure and are **removed**; gates 4, 5 and 6 stay and are renumbered 1, 2 and 3 when the
importer change is built. Gate 6 (size) now measures a much smaller database. Until then the
import report still applies all six gates.
