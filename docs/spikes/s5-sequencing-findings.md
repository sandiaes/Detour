# Spike S5 — Sequencing: simple heuristic versus OR-Tools: findings

- **Date:** 2026-11-12
- **Question (D7):** does OR-Tools give better plans than a simple heuristic within the latency
  budget, repeatably across runs and machines? Time windows are meal windows and the day length
  only; there are no opening hours (ADR 003).
- **Code (throwaway):** `spikes/s5-sequencing/`, workflow `.github/workflows/spike-s5-sequencing.yml`.
- **Verification marks:** ✅ read on the official page on 2026-11-12; ◐ partly read; ✗ not read.

**Status: results pending (benchmark running); this note is completed in the next commit.**

## Method

### Fixtures (hand-made, synthetic)

The imported S2 data was not kept (only counts), so the three trips are generated with a fixed
seed by `make_fixtures.py` and committed as JSON. **They are synthetic:** the visit points, their
categories and their scores are drawn at random around real city centres (the centres used in
spike S3) and are not real places. Travel times are integer minutes from one fixed estimate rule
(straight line × detour factor ÷ speed, the shape of the architecture's `estimated` fallback;
fastest of walking 4.5 km/h, local driving 30 km/h + 12 min, inter-city driving 80 km/h +
20 min). No routing provider was called. Storing integers means neither solver computes floating
point geometry, which would otherwise differ between platforms.

| Fixture | Days | Candidate visits | Day structure |
|---|---:|---:|---|
| `city3-florence` | 3 | 60 in Florence | Days start at the first visit and end after the last (no accommodation, product brief section 9) |
| `region7-tuscany` | 7 | 100 in Florence, Pisa, Siena, Bologna | Every day starts and ends at the base city (Florence); any visit on any day |
| `multi14-italy` | 14 | 160 (40 each in Milan, Venice, Florence, Rome) | Fixed allocation 3 + 3 + 4 + 4 days; a move day leaves at 09:00 and starts at the new city's centre when the fixed drive ends (12:32 to 13:09) |

Rules common to all: day window 09:00–21:00; lunch starts 12:00–14:00 and lasts 60 min; dinner
starts 18:30–19:45 and lasts 75 min; meals have no location (the restaurant is chosen afterwards,
`architecture.md` 5.2 step 5) and may be taken while moving between two items; visit durations
from a category table (30–120 min).

### The objective both sequencers minimise

`total travel minutes + Σ over dropped visits of 2 × score` (score 1–100). One point of score is
"worth" two minutes of travel. The validator recomputes it from the written plan.

### The two sequencers

- **Heuristic** (`heuristic.py`, about 150 lines): greedy insertion of the visit with the largest
  objective gain at its best feasible position, then local search (2-opt within a day; moving a
  visit within or between days; swapping a planned visit for an unplanned one; re-inserting),
  until nothing improves. Fixed loop order, ties broken by identifier, no randomness, no clock.
- **OR-Tools 9.15.6755** (`ortools_seq.py`): routing model with one vehicle per day; each visit an
  optional node (single-node disjunction with the drop penalty); a time dimension of service plus
  travel, capped at 21:00; lunch and dinner as vehicle breaks with start windows; visits of the
  multi-city trip restricted to their city's days. Configurations:

  | Name | First solution | Metaheuristic | Stop |
  |---|---|---|---|
  | `descent` | PARALLEL_CHEAPEST_INSERTION | GREEDY_DESCENT | local optimum |
  | `au-descent` | ALL_UNPERFORMED | GREEDY_DESCENT | local optimum |
  | `gls-s100` | PARALLEL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 100 solutions |
  | `au-gls-s100` | ALL_UNPERFORMED | GUIDED_LOCAL_SEARCH | 100 solutions |
  | `gls-s1000` | PARALLEL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 1,000 solutions |
  | `gls-t2000` | PARALLEL_CHEAPEST_INSERTION | GUIDED_LOCAL_SEARCH | 2 s wall clock (the non-repeatable control) |

  Every configuration except `gls-t2000` also has a 60 s wall-clock cap as a safety net only.

Both sequencers' results are written out through one earliest-start schedule rule
(`common.schedule`), so the output is the same kind of canonical plan, and are then checked by an
independent validator (`validate.py`) that re-reads the fixture and does not reuse the schedule
code. A plan's identity is the SHA-256 of its canonical JSON (every visit, meal and time).

### Repeatability test

Each (fixture, method) pair runs 3 times in one process; the whole bench runs as two separate
processes in a Claude Code cloud container (Intel Xeon, 4 CPUs, Linux x86-64, Python 3.13) and
once on each of three GitHub-hosted runners: `ubuntu-24.04` (x86-64), `ubuntu-24.04-arm`
(arm64) and `windows-2025` (x86-64). Same plan hash everywhere means repeatable.
