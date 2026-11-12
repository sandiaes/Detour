# Spike S5 — Sequencing: simple heuristic versus OR-Tools: findings

- **Date:** 2026-11-12
- **Question (D7):** does OR-Tools give better plans than a simple heuristic within the latency
  budget, repeatably across runs and machines? Time windows are meal windows and the day length
  only; there are no opening hours (ADR 003).
- **Code (throwaway):** `spikes/s5-sequencing/`, workflow `.github/workflows/spike-s5-sequencing.yml`.
- **Verification marks:** ✅ read on the official page on 2026-11-12; ◐ partly read; ✗ not read.

## Recommendation

**Use the heuristic only. Do not adopt OR-Tools (D7).** Keep the `Sequencer` interface so the
question can be reopened, but with one implementation.

1. **OR-Tools plans are somewhat better where it finds them.** Its best repeatable
   configuration (guided local search for 100 solutions) beat the heuristic by 7.5% (city) and
   8.4% (region) on the shared objective; the heuristic collected 1.8% and 5.7% less score. On
   the 14-day trip the heuristic equalled the best OR-Tools plan (1435 against 1436).
2. **OR-Tools is 7 to 300 times slower.** Heuristic 7–43 ms per plan on every machine;
   OR-Tools 0.1–1.3 s for a plain descent and 1.7–4.2 s with guided local search for 100
   solutions, per variant. On the GitHub x86-64 runner two variants with guided local search
   take about 8 s, over the 5 s KPI before the rest of the pipeline. Render's free tier
   (ADR 005) was not measured.
3. **OR-Tools can fail to plan at all.** On the 14-day trip, with days that start late after an
   inter-city drive, every insertion-based first-solution strategy returned *nothing planned*
   after the 60 s cap, on every machine. Only "start with nothing planned" found a plan, in
   18 s. A feasible trip must never come back empty, so the heuristic would be needed as a
   fallback anyway, and the product would then carry two sequencers.
4. **Solution-count limits are repeatable only while the safety cap is never reached.** Every
   configuration that stopped on its own or on its solution count gave the same plan on five
   runs across Linux x86-64, Linux arm64 and Windows. The 7-day trip with 1,000 solutions hit the
   60 s cap on three of four machines and **returned a different plan on the slower runners**
   (2555 instead of 2509). The 2-second time-limited control also differed between machines,
   as expected. And what one "solution" means depends on the first-solution strategy: 100
   solutions took about 2 s with one strategy and 70 ms with another, with a much worse plan.
5. **Modelling OR-Tools correctly is subtle, and mistakes are silent.** A spike modelling bug
   (the unused dummy node, below) produced a plan that OR-Tools reported as solved; only the
   schedule rule and the independent validator caught it.

**What would reopen D7:** the Phase 4 or Phase 6 fixture KPIs (day utilisation, travel share)
show the heuristic falling short on real imported data. Cheaper first steps then: improve the
heuristic (better insertion order, an or-opt move), measured against the same fixtures.

## Results

All 21 (fixture, method) cases produced a plan that passed the independent validator. "No plan"
below means a valid but empty plan (every visit dropped).

### Quality (machines C and W; the three cases that differ on A and L are under Repeatability)

Objective = travel minutes + 2 × score of dropped visits; lower is better.

| Fixture | Method | Objective | Visits | Score | Travel min | Travel share | Day utilisation |
|---|---|---:|---:|---:|---:|---:|---:|
| city3 | **heuristic** | 958 | 24 | 1414 | 186 | 8.7% | 98.9% |
| city3 | descent | 906 | 24 | 1440 | 186 | 8.7% | 98.9% |
| city3 | au-descent | 941 | 27 | 1425 | 191 | 9.0% | 98.4% |
| city3 | gls-s100 | **886** | 24 | 1440 | 166 | 7.8% | 98.0% |
| city3 | au-gls-s100 | 955 | 27 | 1425 | 205 | 9.6% | 99.1% |
| city3 | gls-s1000 | 886 | 24 | 1440 | 166 | 7.8% | 98.0% |
| city3 | gls-t2000 | 886 | 24 | 1440 | 166 | 7.8% | 98.0% |
| region7 | **heuristic** | 2795 | 49 | 2782 | 1125 | 22.9% | 97.6% |
| region7 | descent | 2627 | 50 | 2841 | 1075 | 22.0% | 96.9% |
| region7 | au-descent | 2996 | 48 | 2680 | 1122 | 22.8% | 97.6% |
| region7 | gls-s100 | 2561 | 48 | 2951 | 1229 | 24.8% | 98.2% |
| region7 | au-gls-s100 | 3323 | 45 | 2471 | 1031 | 22.3% | 91.9% |
| region7 | gls-s1000 | **2509** | 47 | 2976 | 1227 | 24.8% | 98.2% |
| region7 | gls-t2000 | 2561 | 48 | 2951 | 1229 | 24.8% | 98.2% |
| multi14 | **heuristic** | **1435** | 99 | 4944 | 903 | 10.0% | 89.8% |
| multi14 | descent | no plan (10420) | 0 | 0 | 0 | | |
| multi14 | au-descent | 1436 | 103 | 4935 | 886 | 9.8% | 89.9% |
| multi14 | gls-s100 | no plan | 0 | | | | |
| multi14 | au-gls-s100 | 4096 | 94 | 3786 | 1248 | 13.7% | 90.7% |
| multi14 | gls-s1000 | no plan | 0 | | | | |
| multi14 | gls-t2000 | no plan | 0 | | | | |

Against the KPIs (`kpis.md`): every plan with visits is inside the travel-share target (≤ 25%);
day utilisation is above the 60–90% band for city3 and region7 with both sequencers, because the
synthetic fixtures always have more candidates than time. That is a fixture property, not a
sequencer difference.

### Latency, median of 3 runs per machine (ms per plan, one variant)

Machines: **C** = Claude Code cloud container (Intel Xeon, 4 CPUs, Linux); **W** = GitHub
`windows-2025`; **A** = GitHub `ubuntu-24.04-arm` (arm64); **L** = GitHub `ubuntu-24.04` (x86-64).
The GitHub runners of a private repository have 2 CPUs (ADR 005). "cap" = stopped by the 60 s
safety cap.

| Fixture | Method | C | W | A | L |
|---|---|---:|---:|---:|---:|
| city3 | **heuristic** | **7** | **11** | **10** | **12** |
| city3 | descent | 100 | 84 | 157 | 218 |
| city3 | au-descent | 134 | 121 | 215 | 257 |
| city3 | gls-s100 | 2,174 | 1,792 | 3,279 | 4,038 |
| city3 | au-gls-s100 | 73 | 68 | 118 | 139 |
| city3 | gls-s1000 | 22,705 | 18,705 | 35,332 | 43,509 |
| city3 | gls-t2000 | 2,002 | 2,002 | 2,002 | 2,001 |
| region7 | **heuristic** | **25** | **24** | **38** | **43** |
| region7 | descent | 672 | 527 | 1,119 | 1,333 |
| region7 | au-descent | 493 | 396 | 818 | 963 |
| region7 | gls-s100 | 2,179 | 1,654 | 3,491 | 4,176 |
| region7 | au-gls-s100 | 86 | 75 | 141 | 157 |
| region7 | gls-s1000 | cap | 54,979 | cap | cap |
| region7 | gls-t2000 | 2,001 | 2,003 | 2,002 | 2,002 |
| multi14 | **heuristic** | **18** | **18** | **28** | **32** |
| multi14 | descent | cap | cap | cap | cap |
| multi14 | au-descent | 18,384 | 18,113 | 19,289 | 19,806 |
| multi14 | gls-s100 | cap | cap | cap | cap |
| multi14 | au-gls-s100 | 13,068 | 13,043 | 13,289 | 13,426 |
| multi14 | gls-s1000 | cap | cap | cap | cap |
| multi14 | gls-t2000 | 2,003 | 2,004 | 2,003 | 2,003 |

The KPI is p95 ≤ 5 s for **two** variants of a trip up to 7 days, for the whole request. On the
GitHub x86-64 runner, `gls-s100` alone takes 4.0–4.2 s per variant: 8 s for two.

### Repeatability

Within each machine, every method gave the same plan on all 3 repeats (and on both container
processes), including the time-limited control. Across the five runs (C twice, W, A, L):

| Fixture | Method | Same plan on all machines? |
|---|---|---|
| all three | **heuristic** | **yes** |
| all three | descent, au-descent, gls-s100, au-gls-s100 | yes |
| city3, multi14 | gls-s1000 | yes |
| **region7** | **gls-s1000** | **no**: objective 2509 on C and W, 2555 on A and L. W finished 1,000 solutions in 55 s; C, A and L hit the 60 s safety cap at different points. |
| **city3** | **gls-t2000** | **no**: 886 on C and W, 890 on A and L |
| **region7** | **gls-t2000** | **no**: 2561 on C and W, 2627 on A and L |
| multi14 | gls-t2000 | yes (no plan everywhere) |

So the architecture's rule "bound the search by solution count; wall clock only as a safety cap"
holds only while the cap is never reached. On region7 a 1,000-solution limit needed 55–60 s,
the cap was reached on 3 of 4 machines, and the plan changed with the machine. A cap that is
never reached gives no protection against slow solves; a cap that is reached breaks golden
tests. The heuristic has neither problem.

## Problems found on the way (and fixed in the spike)

| Problem | Effect | Fix |
|---|---|---|
| The zero-travel dummy node for free day starts was added even when no day used it | OR-Tools treated it as a mandatory ordinary node and routed through it: a teleport mid-route, reported as solved. The schedule rule and validator rejected the plan. | Create the dummy only when a day needs it |
| A move day's inter-city drive was only paid if a visit was planned that day | The heuristic left move days empty and "teleported" between cities for free | The drive is fixed: a move day starts at the new city's centre when the drive ends |
| `SetAllowedVehiclesForIndex` rejected a Python list in OR-Tools 9.15.6755 (SWIG type error) | Model could not be built | Restricted `VehicleVar(index)` to the allowed days plus -1 instead |
| Meal breaks first linked to each day's start and end with generic constraints | Suspected cause of the stall | Removed; the stall remained, so it is not the cause |

## Facts relied on (read 2026-11-12)

| Fact | Source |
|---|---|
| OR-Tools 9.15.6755, released 2026-01-14, Apache 2.0, wheels for Python 3.9–3.14 on Linux x86-64 and arm64, macOS, Windows x86-64 | ✅ <https://pypi.org/project/ortools/> |
| `solution_limit`: "Limit to the number of solutions generated during the search"; `time_limit`: limit "to the time spent in the search"; `lns_time_limit`: limit "to the time spent in the completion search for each local search neighbor" | ✅ <https://developers.google.com/optimization/routing/routing_options>, routing_parameters.proto on GitHub |
| GUIDED_LOCAL_SEARCH "is generally the most efficient metaheuristic for vehicle routing"; dropped visits through disjunctions with penalties | ✅ routing_options page; <https://developers.google.com/optimization/routing/penalties> |
| Determinism, threading and vehicle breaks | ✗ **not documented** on the pages read; the proto has no seed or thread field. The `lns_time_limit` default reported by the library at run time was 100 ms (a wall-clock limit inside the search; the configurations here use no LNS operator that it governs, and the plans were identical across machines) |
| GitHub runner rates used for cost: Linux x64 $0.006, Linux arm64 $0.005, Windows $0.010 per minute | ✅ <https://docs.github.com/en/billing/concepts/product-billing/github-actions> |

## Limits of this spike

- Synthetic fixtures with estimated travel times; real places cluster differently, and routed
  times are less regular. The size of the quality gap could change on real data.
- One objective weighting (2 minutes per score point) and only two meals; no stability cost
  (Phase 7) and no strategy profiles (Phase 4).
- The heuristic is a first version; its gap to OR-Tools is an upper bound on what a better
  heuristic would leave.
- Latency measured on a 4-CPU cloud container and GitHub runners, not on Render's free tier.

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
processes in a Claude Code cloud container (Intel Xeon, 4 CPUs, Linux x86-64, Python 3.13.18) and
once on each of three GitHub-hosted runners: `ubuntu-24.04` (x86-64), `ubuntu-24.04-arm`
(arm64) and `windows-2025` (x86-64), Python 3.13 (workflow run 43218210425, 2026-11-12). Same
plan hash everywhere means repeatable. CI cost of the two workflow runs: about 100 runner
minutes, roughly $0.70 of the $12 monthly allowance at the rates below.
