# ADR 013 — Phase 3: the travel-time service, its cache and its request shape

- **Status:** **Proposed** on 2026-11-12. The code is built and tested; the owner confirms or
  changes the decisions in section "Decision". Two open items (request-shape check, smaller route
  request) need the owner's browser check before the cache is trusted for planning.
- **Date:** 2026-11-12
- **Related:** [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md),
  [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`009-region-readiness-thresholds.md`](009-region-readiness-thresholds.md),
  [`../spikes/fossgis-matrix-check.md`](../spikes/fossgis-matrix-check.md),
  [`../spikes/fossgis-request-shape-check.md`](../spikes/fossgis-request-shape-check.md),
  [`../data-model.md`](../data-model.md), [`../architecture.md`](../architecture.md) section 4.5

## Context

ADR 004 allowed one named exception: backend code may call the FOSSGIS Valhalla server for walking
and driving times, through an adapter, within its rate rules. Phase 3 builds that adapter, the
cache and the estimate fallback. ADR 004 also left open: how to fix the request shape, whether a
request option shrinks the response, and why one pair got 523 s in two requests and 653 s in a
third.

## What could and could not be checked (2026-11-12)

The build environment's network policy refuses `valhalla1.openstreetmap.de`
(`connect_rejected`) and the host `valhalla.github.io`. **No request was made to the FOSSGIS
server and the Valhalla API reference was not read.** What was read:

- Valhalla's source on GitHub (raw files `src/thor/matrix_action.cc`, `costmatrix.cc`,
  `timedistancematrix.cc`, `src/loki/matrix_action.cc`, default branch, read 2026-11-12). The
  reading was done by a model, and `costmatrix.cc` was truncated; it is a **lead, not a verified
  fact**. It reports: error 150 compares `sources x targets` with the limit (so 100 cells);
  error 154 is a straight-line check between each source and target; for walking the server picks
  the time-distance algorithm if either side has at most 5 locations and the cost-matrix
  algorithm if both have more; for driving without a start time it uses the cost matrix; no
  request option selects the algorithm.

The response sample the owner pasted is the only record of response formats. Everything else that
the adapter assumes is marked **unverified** below.

## The 523 s / 653 s difference: not determined

The question was to find the cause and report whether the difference persists. **Neither could be
done from here.** What can be said:

- The reading above predicts 2 x 2 and 20 x 5 walking requests use the *same* algorithm (each has
  a side of at most 5), but 10 x 10 a different one. The owner saw 523 s for 2 x 2 **and** 10 x 10
  and 653 s for 20 x 5, with different algorithm names across the three. So the algorithm choice
  alone does not explain the numbers, or the reading is wrong, or the server is configured
  differently from the repository's default. The code reading also lists real reasons two
  algorithms can differ (partial first and last edges, a snap penalty, different paths on ties),
  none shown to account for 25% on 662 m.
- It is unknown whether the difference **persists** (the same request again, hours later).

So the cache is built so that it **cannot silently mix shapes** and the check is prepared for the
owner (`docs/spikes/fossgis-request-shape-check.md`, eight clicks, with the rule for reading each
outcome). Until it is done, treat cached routed times as unconfirmed for comparing two itineraries
by small differences. The adapter does not depend on the answer to be correct and safe; the answer
decides whether `matrix-v1` is the right shape.

## Decision

1. **One fixed request shape, `matrix-v1`:** every matrix request has exactly one source and 1 to
   100 targets, a JSON body of exactly `sources`, `targets` and `costing`, and coordinates rounded
   to 1e-5 degree (about 1.1 m; the request is built from the stored integers). Walking is
   `pedestrian`, driving `auto`. One source keeps every cell on the same kind of request whatever
   the batch; it is also the shape that packs a sparse set (each place against its neighbours)
   with no waste. **Cost:** a dense matrix needs one request per source, so 50 places need 50
   requests, against about 25 for a 10 x 10 block shape. At 1 call per second, 50 requests take
   about 40 seconds after the burst. Phase 4 must therefore plan **sparse** cell sets and pass a
   `max_seconds` limit (cells not reached are estimated and labelled). If the owner's check shows
   a block shape is consistent, the shape changes by version, not by editing rows.
2. **Chunking.** At most 100 cells per request (ADR 004). Cells farther apart than 148.5 km go to
   the single-route request, one per leg. The 150 km limit is the server's; the 1.5 km margin
   covers a distance function that was not read. A given pair always takes the same path, so its
   time never mixes shapes. Plans are sorted, hence deterministic.
3. **Rate and safety**, all enforced in code, with the ADR 004 caps as hard validator limits on
   configuration: token bucket, 1 call per second, burst 10, starting full (a restarted process
   may burst once; the instance is single-process); a circuit breaker that opens after **any**
   429, error response, timeout or unreadable body (60 s, doubling to 15 min; 5 min after a 429,
   or the server's `Retry-After` if longer; one probe call when half-open); a timeout of 10 s; a
   daily budget of 1,500 calls in `app.provider_usage`, reserved before each call. The budget,
   the timeout and the cache cap are **our own limits, not FOSSGIS figures**. A call that waits
   longer than 5 s for a token is not made: its cells are estimated. `User-Agent` and
   `X-Client-Id: detour-travel-planner` are sent on every call.
   Known limit: a valid "no path" answer arrives as an HTTP error, and the literal ADR 004 rule
   opens the breaker for it too. That pauses all routing for a minute and the cell is not cached.
   Accepted for now (conservative toward the server); the response was not seen, so it cannot be
   told apart safely.
4. **Cache: `geo.travel_time`**, rebuilt by migration `0005` (it had never been written; the
   migration refuses to run if it holds rows). A cell is its two end points as integers of 1e-5
   degree, not a place id, so a place that moves in a later import cannot keep a stale time. The
   key includes `mode` and `request_shape`; each row stores `provider`, `response_date` (the
   server's `Date` header, else our clock), `algorithm` (the name the response gave) and the
   numbers. A routed row never expires. **A null cell** is stored as an `estimated` row with **no
   numbers** and a `retry_after` 30 days ahead: the estimate is recomputed on every read from the
   current rules, so changing the estimate factors never leaves stale numbers. **Estimates made
   because the provider was unavailable (off, breaker open, budget, rate limit, time limit) are
   not stored**: they say nothing about the provider and a later call may do better. Raw
   responses are not stored per cell; a cell's response is its distance and time, which are, and
   the algorithm.
5. **Size.** Gate 6 of ADR 009 sums every table in `geo`, so the cache counts. It is capped at
   100,000 rows (oldest response first). **Measured 2026-11-12 on PostgreSQL 16 with 100,000
   realistic rows: 20.7 MB (207 bytes a row: 13.4 MB table, 7.2 MB index)**, 8% of the 250 MB
   gate. Austria alone is about 33 MB (owner's figure), so five regions plus a full cache stay
   inside the gate. The cap is a setting (`DETOUR_ROUTING_CACHE_MAX_ROWS`, at least 1,000).
6. **Estimate fallback** (`travel/estimate.py`, version `2026-11-12.1`): straight-line distance
   times a detour factor of 1.3, then a speed: walking 4.5 km/h; driving 30 km/h for the first
   25 km of path and 80 km/h beyond. **These are our assumptions, not measured or provider data;**
   they are always labelled `estimated` with a reason code. Two identical points give 0 s, 0 m,
   labelled `estimated` (`same_point`), with no request. A provider answer of 0 s and 0 m for
   points more than 25 m apart is treated as no route.
7. **Route geometry** is fetched only by `route_geometry()`, for the selected itinerary, returned
   to the caller and **never cached or archived** (ADR 006); it makes one route request and
   counts against the budget. If the provider cannot give it, `None`: no line is invented.
8. **Response size of the route request.** Documented options (`directions_type: none`, and
   `shape_format: no_shape` when only the time is wanted) are implemented behind
   `DETOUR_ROUTING_SLIM_ROUTE_REQUESTS`, **off by default because they are unverified**: I
   believe from memory that both exist; the API reference could not be read. Request H of the
   owner's check tests it. The matrix response is small (about 70 bytes a cell, 7 KB at the
   limit) and no option was looked for.
9. **No other provider.** No second routing source, no paid fallback; when the adapter cannot
   answer, the estimate is used.

## Unverified assumptions in the adapter

| Assumption | Where | If wrong |
|---|---|---|
| A null cell is JSON `null`, or an object with null `time` and `distance` (or either missing) | `parse_matrix` | A different shape raises, opens the breaker, estimates are used; nothing wrong is stored |
| `units` is `kilometers` when present | both parsers | Another unit is refused, not converted |
| `POST` with a JSON body is accepted on `/sources_to_targets` and `/route` (the owner's checks used `GET ?json=`) | `_post` | The first call fails and opens the breaker: **the owner's first real use will show this** |
| The route `shape` is an encoded polyline with six decimals | `decode_polyline6` | Wrong coordinates would be drawn; out-of-range points are refused. Check with a known route |
| `directions_type` / `shape_format: no_shape` exist | slim option | Off by default |
| The matrix distance limit is straight-line (the source reading says so) | chunking | The margin absorbs small differences; a refusal opens the breaker |

The contract tests use fixtures in the documented format, **not live recordings**
(`services/api/tests/fixtures/valhalla/README.md`). They must be replaced by real recordings after
the owner's check.

## Alternatives

| Alternative | Why not chosen |
|---|---|
| Block shape (10 x 10) | About half the requests for a dense matrix, but cells then come from differently sized requests, which is the suspected source of the 523/653 difference. Revisit after the check |
| Store estimates for every miss | A cache full of numbers that say nothing about the provider, growing the `geo` schema |
| Key the cache by place id | A place that moves keeps a wrong time; two places at one point need two rows |
| Store the raw response per cell | Adds size for no information beyond distance, time and algorithm |
| Check the breaker only for 429 | ADR 004 says "any 429 or error"; kept literal |

## Consequences

- Phase 4 gets `TravelTimeService.cells()`, `matrix()`, `travel_time()` and `route_geometry()`
  (on `app.state.travel_time`); no endpoint was added, the API contract is unchanged.
- Every transfer carries `confidence` (`routed` or `estimated`), `source` and, for estimates, a
  reason; the label is the one `app.transfer.confidence` already accepts.
- The first dense request for a big city is slow by design; Phase 4 owns the sparse plan.
- The breaker and limiter are per process. A second API process would double the rate.

## Open items (owner)

1. Run `docs/spikes/fossgis-request-shape-check.md` (eight clicks) and record the results here.
2. Notify FOSSGIS via GitHub Discussions before the app is published to end users (ADR 004).
3. Confirm or change the numbers in decisions 3, 5 and 6.
