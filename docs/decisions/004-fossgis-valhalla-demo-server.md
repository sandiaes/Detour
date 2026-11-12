# ADR 004 — FOSSGIS Valhalla demo server as the MVP travel-time provider

- **Status:** **Accepted** on 2026-11-12 (owner approval). CLAUDE.md and ADR 002 were amended
  in the same change. The manual matrix check is recorded below and in
  `docs/spikes/fossgis-matrix-check.md`.
- **Date:** 2026-11-12
- **Related:** [`001-technology-stack.md`](001-technology-stack.md),
  [`002-api-strategy.md`](002-api-strategy.md), [`../app-plan.md`](../app-plan.md) (D3, D14),
  spike S3

## Context

The owner has no server and wants free, managed services (D14). Supabase can hold the database,
but neither Supabase nor Firebase can run a Valhalla routing engine. Spike S3 measures what
Italy needs when self-hosted. FOSSGIS e.V. runs a public Valhalla server with a planet graph.

## What the official sources say (read 2026-11-12)

Read:

- Valhalla README, "Demo Server" section: the server "is open to the public and includes a full
  planet graph". "Usage of the demo server follows the usual fair-usage policy as OSRM &
  Nominatim demo servers (somewhat enforced by rate limits)." For apps published to end users:
  "let us know via Github Discussions and … include an identifying `X-Client-Id` request
  header, e.g. `X-Client-Id: newroutingapp.io`."
- Valhalla discussion 3373, maintainer comment of 2021-11-15: "we rate limit to 1
  call/user/sec and 100 calls/sec total. Service limits are a bit stricter than the defaults as
  well."
- Same discussion, maintainer comment of 2026-09-05: "we do allow for bursts of 10" and
  "Service limits are a lot stricter now". Comment of 2024-02-27: "A proper User-Agent header is
  always appreciated".
- The opening post says limits "will have to be fairly strict for the computationally expensive
  ones like `/expansion`, `/centroid` or `/matrix`", without numbers.

Not read (the pages could not be fetched): `valhalla.openstreetmap.de` itself and FOSSGIS's own
article about the service. **No page read states a matrix size limit, a per-day quota, or how a
block works or is lifted.** Third-party developers' comments in the discussion are not policy.

## Proposed decision

Allow one named exception: the FOSSGIS Valhalla server is used for walking and driving travel
times, through a provider adapter, for a personal-scale, non-commercial app.

Conditions:

1. **Adapter rules apply in full:** timeout, cache, daily budget counter, fallback,
   `User-Agent` and `X-Client-Id` headers naming the project.
2. **Rate:** at most 1 request per second sustained, never more than a burst of 10, with a
   circuit breaker that stops calling for a period after any 429 or error response.
3. **Cache first:** every returned time is stored in `geo.travel_time` with the provider, the
   response date and the request mode. Plan generation reads the cache; a miss calls the
   adapter; a failure or a skipped call uses the labelled estimate.
4. **Fallback:** straight-line distance times a mode factor, labelled `estimated`.
5. **Tests and CI never call the server.** Contract tests use recorded responses.
6. **Notify FOSSGIS** via GitHub Discussions before the app is published to end users. This is
   the owner's action.
7. **Revisit** if the server throttles or blocks the app, if its terms change, or if S3 shows
   self-hosting is affordable.

Rules this would amend, if approved:

- CLAUDE.md: "Do not call public community servers (… FOSSGIS routing …) from code, tests or
  the app" gains the exception above (code only, never tests).
- CLAUDE.md and ADR 002: "Plan generation makes no third-party network calls" becomes "except
  uncached travel times through the routing adapter".
- `app-plan.md` section 1 (community servers are development-only).

## Alternatives

| Alternative | Why not chosen as the default |
|---|---|
| Self-host Valhalla | No server available; S3 measures whether a free machine could hold one country. Stays the fallback. |
| Hosted routing API with a free tier | Small quotas, unverified terms (ADR 001); each needs its own ADR. |
| Straight-line estimates only | Zero dependency but the weakest plans; kept as the fallback. |

## Risks and unknowns

- **Matrix limit measured (owner, by hand, 2026-11-12):** 2 x 2 and 10 x 10 pedestrian
  matrices worked (the 10 x 10 took about 1 second); 25 x 25 and 50 x 50 were refused with
  `error_code` 150, "Exceeded max locations: 100.000000". The consistent reading is a limit of
  100 cells (sources x targets) per request; a follow-up in `docs/spikes/fossgis-matrix-check.md`
  confirms it. At that size a full 50 x 50 matrix needs 25 requests, so Phase 3 must plan
  sparse matrices (each place against a bounded set of neighbours) and cache every cell.
- **No availability promise.** The operators can throttle or block at any time.
- **Data versions.** Their OSM snapshot differs from our `geo` extract, so a time can describe a
  road that our data lacks. Determinism then rests on the cache and recorded responses, not on
  our own data version.
- **Scope of "personal".** Publishing to other users raises load and requires notification.
- **Request volume is unmeasured.** No estimate of calls per itinerary exists yet.

## Consequences if accepted

- D3 reduces to the database and a small API host; Valhalla is no longer hosted by us.
- Phase 3 builds the adapter, cache and estimate fallback instead of a Valhalla container.
- S3 results remain the reference for a later move to self-hosting.
