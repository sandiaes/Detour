# Manual check: why one pair got two different times, and a smaller route request

One-time, by hand, in a normal browser (ADR 013, open items). Not code, not a test. It follows the
same rules as the earlier checks in [`fossgis-matrix-check.md`](fossgis-matrix-check.md): click the
links **in order, one at a time, waiting at least 10 seconds between clicks**, and stop at the
first one that fails. Eight clicks in all. Do not repeat a refused one.

**Why this is needed.** The same pair (point 0 to point 1, 0.662 km) took 523 s in the 2 x 2 and
10 x 10 requests and 653 s in the 20 x 5 request. The routing adapter cannot be trusted to fill a
cache until we know whether that difference is real and what causes it. It could not be tested from
the build environment (the server is not reachable from it). Everything below uses pedestrian
costing and the same Florence grid as before.

**What the source code suggests (a lead, not a fact).** A model-assisted reading of Valhalla's
source on 2026-11-12 (not checked by a person; see ADR 013) says the server picks one of two
matrix algorithms from the number of sources and targets (for walking: the faster one if either
side has 5 or fewer, the other if both have more). That reading predicts 2 x 2 and 20 x 5 would use
the **same** algorithm, which contradicts what you saw, so it does not explain the difference.
Requests D and F and the `algorithm` field in each answer settle which is true.

| # | Request | What it shows | Link |
|---|---|---|---|
| A | point 0 to point 1 only (1 source x 1 target, 1 cell) | the pair alone | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| B | 1 source x 10 targets (10 cells) | the shape the service will use | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| C | 2 x 2 (4 cells) | repeat of the first check (523 s) | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| D | 20 x 5 (100 cells) | repeat of the follow-up (653 s) | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| E | 20 x 5 again | does the number change from one request to the next? | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.235%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2402%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2454%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2454%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| F | 6 x 6 (36 cells) | both sides above 5 | [open](https://valhalla1.openstreetmap.de/sources_to_targets?json=%7B%22sources%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%5D%2C%22targets%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7696%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7732%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7768%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.235%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| G | single route, point 0 to point 1, walking | what a plain route says | [open](https://valhalla1.openstreetmap.de/route?json=%7B%22locations%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%7D) |
| H | same route with `directions_type` none and `shape_format` no_shape | does the smaller request work, and how much shorter is it? | [open](https://valhalla1.openstreetmap.de/route?json=%7B%22locations%22%3A%5B%7B%22lat%22%3A43.7624%2C%22lon%22%3A11.2298%7D%2C%7B%22lat%22%3A43.766%2C%22lon%22%3A11.2298%7D%5D%2C%22costing%22%3A%22pedestrian%22%2C%22directions_type%22%3A%22none%22%2C%22shape_format%22%3A%22no_shape%22%7D) |

## What to send back

For **A to F** (matrix requests), from each page:

- the `time` and `distance` of the cell from point 0 to point 1: the only cell in A, and the
  second cell of the first row in B to F;
- the word after `"algorithm":` (near the end of the page);
- the whole error text instead, if the request was refused.

For **G**: `trip.summary.time` (seconds) and `trip.summary.length` (km).

For **H**: worked or not (full error text if not), `trip.summary.time` and `trip.summary.length`,
and two yes/no answers: does the page still contain the word `maneuvers`? does it still contain a
`shape` line? Also say roughly how much shorter the page is than G's (for example "a few lines
instead of a screenful").

Do not share anything else from the pages.

## How the answers are read

| If | Then |
|---|---|
| A, B, C give 523 s and D, E, F give 653 s, and `algorithm` differs | The difference is the algorithm, and it depends on the request shape. The adapter's 1 x N shape is right only if B matches the route in G; if not, ADR 013 changes the shape and the cache version (rows of the old shape are ignored automatically). |
| D and E differ from each other | The time changes between identical requests: the cache cannot be trusted until the cause is known. Stop and report. |
| All six agree | The earlier difference does not persist; it was something else (for example a different server instance or data update). Record it and trust the cache. |
| G matches B but not D | Walking times from 1 x N requests agree with a plain route, which is the best available reference. |
| H works and is much shorter | Switch on `DETOUR_ROUTING_SLIM_ROUTE_REQUESTS=true` (it is off by default) and record the size difference in ADR 013. |
| H is refused | Leave it off and record the error text. |

Record the date and the results in ADR 013, section "Open items", and keep the pasted figures here
under a "Result" heading, as the earlier checks do.
