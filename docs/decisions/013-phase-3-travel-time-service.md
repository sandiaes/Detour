# ADR 013 — Phase 3: the travel-time service, its cache and its request shape

- **Status:** **Proposed** on 2026-11-12. The code is built and tested; the owner confirms or
  changes the decisions in section "Decision". The owner's request-shape check was run on
  2026-11-12 and is recorded below.
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
server from the build environment and the Valhalla API reference was not read.** The owner then ran
the eight-request check by hand (`docs/spikes/fossgis-request-shape-check.md`, results there); the
real responses are the contract-test fixtures (`tests/fixtures/valhalla/*-recorded.json`).

Valhalla's source on GitHub was also read (raw files `src/thor/matrix_action.cc`, `costmatrix.cc`,
`timedistancematrix.cc`, `src/loki/matrix_action.cc`, default branch, read 2026-11-12). The reading
was done by a model and `costmatrix.cc` was truncated, so it was a lead. It reported: error 150
compares `sources x targets` with the limit; error 154 is a straight-line check; for walking the
server picks the time-distance algorithm if either side has at most 5 locations and the cost
matrix if both have more; driving without a start time uses the cost matrix; no request option
selects the algorithm. **The owner's check confirmed the algorithm rule** (6 x 6 used
`costmatrix`; every request with a side of 5 or fewer used `timedistancematrix`).

## The 523 s / 653 s difference (owner's check, 2026-11-12)

| Request | Algorithm | Pair 0 to 1 |
|---|---|---|
| 1 x 1, 1 x 10, 2 x 2 | `timedistancematrix` | 523 s |
| 6 x 6 | `costmatrix` | 523 s |
| plain route | n/a | 523.995 s |
| **20 x 5**, twice | `timedistancematrix` | **653 s**, both times, all 100 cells identical |

- **Does it persist?** Yes, for that request: repeating it gives identical numbers, so it is
  deterministic, not drift.
- **Cause:** **not known.** It is not the algorithm (the 20 x 5 request used the same one as the
  523 s requests). Something about a request with 20 sources changes the numbers, in both
  directions (0 to 2: 1,746 s against 1,806 s; 0 to 4: 2,245 s against 2,183 s).
- **What is known:** the 1 x N shape agrees with the plain route and with the cost matrix: five
  comparable cells between the 1 x 10 and the 6 x 6 had identical times and distances within 2 m.
  The odd request is the shape the adapter does not use.
- **Residual risk:** one pair in one part of Florence, and no 1 x 50 or 1 x 100 request was tried.
  The 20 x 5 result shows that how a request is composed can matter, so the shape stays versioned
  and the algorithm is stored with every cell. An optional follow-up: one 1 x 50 request against
  the plain routes of three of its cells.

The cache can therefore be trusted for 1 x N rows to the extent of this evidence.

## Decision

1. **One fixed request shape, `matrix-v1`:** every matrix request has exactly one source and 1 to
   100 targets, a JSON body of exactly `sources`, `targets` and `costing`, and coordinates rounded
   to 1e-5 degree (about 1.1 m; the request is built from the stored integers). Walking is
   `pedestrian`, driving `auto`. One source keeps every cell on the same kind of request whatever
   the batch; it is also the shape that packs a sparse set (each place against its neighbours)
   with no waste. **Cost:** a dense matrix needs one request per source, so 50 places need 50
   requests, against about 25 for a 10 x 10 block shape. At 1 call per second, 50 requests take
   about 40 seconds after the burst. Phase 4 must therefore plan **sparse** cell sets and pass a
   `max_seconds` limit (cells not reached are estimated and labelled). A block shape was not
   tested for consistency (the one tested, 20 x 5, was the outlier); changing shape later is a
   version change, not an edit of rows.
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
   they are always labelled `estimated` with a reason code. **Compared with the owner's real
   walking times (nine cells of the 1 x 10 request, 370 m to 1.6 km straight-line, one part of
   Florence): the speed is about right (real 4.4 to 5.2 km/h, estimate 4.5) but the detour factor
   is too low: real routed distance was 1.66 to 4.29 times the straight line (median 1.97), so
   the estimate was 0.30 to 0.84 of the real time (median 0.72). A thin sample, not a
   calibration; see open items.** Two identical points give 0 s, 0 m,
   labelled `estimated` (`same_point`), with no request. A provider answer of 0 s and 0 m for
   points more than 25 m apart is treated as no route.
7. **Route geometry** is fetched only by `route_geometry()`, for the selected itinerary, returned
   to the caller and **never cached or archived** (ADR 006); it makes one route request and
   counts against the budget. If the provider cannot give it, `None`: no line is invented.
8. **Response size of the route request.** `directions_type: none` is sent on every route
   request (`DETOUR_ROUTING_SLIM_ROUTE_REQUESTS`, on by default). Checked by the owner on
   2026-11-12: the maneuvers disappear and a 662 m walk went from 2,214 to 896 bytes (-60%); on a
   long drive the saving is larger because the directions grow with the route. `shape_format:
   no_shape` was also tried and **did not remove the shape on this server**, so it is not sent;
   the shape stays in every route answer, and a leg's time request therefore still carries its
   line. The matrix response is about 70 bytes a cell (about 7 KB at the limit) and no option was
   looked for.
9. **No other provider.** No second routing source, no paid fallback; when the adapter cannot
   answer, the estimate is used.

## Assumptions in the adapter

Checked against the owner's recorded responses on 2026-11-12:

| Assumption | Status |
|---|---|
| `units` is `kilometers`; matrix `time` is whole seconds, route `time` fractional | **Confirmed**; extra fields (`cost`, headings) are ignored |
| Matrix answer is `sources_to_targets` with `from_index` and `to_index` | **Confirmed** |
| The route `shape` is an encoded polyline with six decimals | **Confirmed**: decoding the recorded shape starts and ends on the snapped points to 1e-6 |
| `directions_type: none` exists | **Confirmed**; `shape_format: no_shape` is **not honoured** |
| The matrix distance limit is straight-line | Source reading only (error 154 earlier); the margin absorbs differences |

Still **unverified**:

| Assumption | Where | If wrong |
|---|---|---|
| A null cell is JSON `null`, or an object with null `time` and `distance` (or either missing); no unreachable cell was in the owner's samples | `parse_matrix` | A different shape raises, opens the breaker, estimates are used; nothing wrong is stored |
| `POST` with a JSON body is accepted on `/sources_to_targets` and `/route` (the owner's checks used `GET ?json=`) | `_post` | The first call fails and opens the breaker: **the first real use will show this** |
| A 1 x 100 request agrees with the plain route as 1 x 10 did | chunking | A wrong time would be cached for that shape; see the optional follow-up above |

The fixtures `*-documented.json` (null cell, long route) are still documented-format, not
recordings; the `*-recorded.json` ones are real
(`services/api/tests/fixtures/valhalla/README.md`).

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

1. Confirm or change the numbers in decisions 3, 5 and 6, in particular the walking detour
   factor (1.3), which the first real data says is low.
2. Optional: one 1 x 50 request against three plain routes, to extend the shape check to a larger
   batch.
3. ~~Notify FOSSGIS~~ Not needed: the owner decided on 2026-11-12 that the app is for the owner and
   one other person only (see the addendum in ADR 004). Revisit if it is ever shared more widely.
