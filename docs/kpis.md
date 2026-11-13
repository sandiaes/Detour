# KPIs

Status: **proposed targets**. Numbers are starting points to be confirmed after the Phase 0
spikes and tuned with real fixtures. Each KPI names how it is measured; none requires an
analytics SDK.

Measurement sources:

- **Fixture suite:** a fixed set of destinations and durations per pilot region, run in CI.
- **Backend logs:** structured request logs with per-stage timings and outcome fields.
- **Import reports:** the data quality report produced by each region import.

## 1. Planning quality

| KPI | Definition | Target | Source |
|---|---|---|---|
| Variant count | Share of plan requests returning at least two itineraries | ≥ 95% of fixtures; the rest return the explicit single-plan response | Fixture suite |
| Variant diversity | Jaccard similarity of the visit sets of the two variants | ≤ 0.6, or different base cities or days per base (areas) | Fixture suite |
| Feasibility | Generated itineraries passing the independent validator | 100% | Fixture suite, logs |
| Day utilisation | Planned time (visits, meals, transfers, inter-city drives) as a share of the 09:00–21:00 window | 60–90% | Fixture suite |
| Meals in their windows | Planned meals that start and end inside their meal window (ADR 016) | 100% | Validator |
| Travel share | Transfer and inter-city time as a share of planned time, Essentials profile | ≤ 25% | Fixture suite |
| Determinism | Identical output for identical input, data version and engine version | 100% | Golden tests |

## 2. Editing and recalculation

| KPI | Definition | Target | Source |
|---|---|---|---|
| Locked-item stability | Locked items moved by a recalculation | 0 | Tests, logs |
| Disruption on add | Existing items changing day after one added location in the same city | ≤ 20% | Fixture suite |
| Diff fidelity | Accepted diffs whose applied result equals the preview | 100% | Tests |
| Restaurant placement acceptance | Proposed slot accepted without choosing an alternative | ≥ 70% | Backend logs: `restaurant_slots_suggested` (`slots`, best first) and `change_previewed` (`slot`) per itinerary |
| Recalculation acceptance | Preview diffs accepted rather than discarded | ≥ 70% | Backend logs |

## 3. Performance

| KPI | Definition | Target | Source |
|---|---|---|---|
| Plan generation latency | p95 time to return two variants for a trip of up to 7 days | ≤ 5 s | Backend logs |
| Recalculation latency | p95 time to return a preview diff | ≤ 3 s | Backend logs |
| Restaurant placement latency | p95 time to return the proposal and alternatives | ≤ 2 s | Backend logs |
| Search latency | p95 for destination and place search on local data | ≤ 300 ms | Backend logs |
| App start to trip list | Cold start on a mid-range Android device | ≤ 3 s | Manual measurement |

## 4. Data quality and transparency

| KPI | Definition | Target | Source |
|---|---|---|---|
| Routed travel share | Transfers with `routed` rather than `estimated` confidence | ≥ 95% | Backend logs |
| Cuisine coverage | Restaurants with a normalised cuisine | Reported per region | Import report |
| Meals planned | Meals of the profiles on days with visits that found a place to eat within 3 km | Reported per fixture; every gap explained in a note | Fixture suite |
| Unlabelled estimates | Estimated or unknown values shown without a label | 0 | UI review checklist |
| Region readiness | Pilot regions passing the minimum data thresholds set after spike S2 (ADR 009; computed by every import since Phase 2, a region is `available` only if all six gates pass) | 100% of enabled regions | Import report |

## 5. Cost and provider dependence

| KPI | Definition | Target | Source |
|---|---|---|---|
| External API spend | Monthly charges from any data or API provider | 0 | Billing review |
| Quota headroom | Peak daily calls to each quota-limited or fair-use provider against its published or self-imposed limit | ≤ 50% | Provider budget counters |
| Runtime external calls per plan | Calls to third-party services during plan generation | 0 | Backend logs |
| Provider switch time | Time to move tiles or search to the fallback provider | ≤ 1 hour, no app release | Phase 9 rehearsal |
| Runtime LLM calls | Calls to any generative model | 0, enforced by dependency review | CI dependency check |

## 6. Reliability and engineering health

| KPI | Definition | Target | Source |
|---|---|---|---|
| Graceful degradation | Core flows completing with routing, search or FX unavailable | 100% of defined scenarios | Phase 9 chaos checks |
| Crash-free sessions | Sessions without a crash during closed testing | ≥ 99% | Play Console pre-launch and testing reports |
| Engine test coverage | Line coverage of the planning engine and validator | ≥ 85% | CI |
| Contract drift | Mismatches between the OpenAPI contract and generated app types | 0 | CI |
| Attribution compliance | Required credits present on map and About screen | 100% | Release checklist |

## 7. Platform readiness

| KPI | Definition | Target | Source |
|---|---|---|---|
| Platform-specific code | Share of app source files with Android-only code paths | ≤ 5% | Repository scan |
| Android-only native dependencies | Dependencies without iOS support | 0 | Dependency review |

## 8. Measurements

**Phase 4 (2026-11-12, synthetic fixtures, Claude Code cloud container; ADR 014):** two plans on
every fixture that can support them, each passing the validator; Jaccard 0.46 to 0.59; travel share
(Essentials) 10.6 to 11.0 %; day utilisation 74 % (Essentials) and 82 % (Wider) for 3 and 7 days,
63 % and 52 % for 14 days in one city (below the band: the city runs out of distinct sights);
engine time for two variants 54 ms (3 days), 176 ms (7 days), 610 ms (14 days); 0.37 s for a 7-day
plan through the API, without the routing provider. The routed-share KPI is not met on a cold cache
(provider time is capped at 3 s per generation). Golden tests pin the output. Planner line coverage
is 92 to 100 % per module. Not yet measured on real data or on Render.

## 9. Review cadence

- Fixture and golden KPIs: every CI run.
- Latency, routed share and quota headroom: at the end of each phase from Phase 4 onward.
- Acceptance-rate KPIs: during the Phase 9 closed test.
- Targets are revisited once after Phase 0 and once after Phase 6.
