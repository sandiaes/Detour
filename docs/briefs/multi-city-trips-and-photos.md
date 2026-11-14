# Brief: explicit multi-city trips, and photos that load themselves

Written 2026-11-14 for a fresh session. Nothing in this brief is built or decided. Read
`CLAUDE.md` first and follow its rules (ADR before a new feature or provider, no invented data,
no LLM, `geo`/`app` separation, deterministic planner, every itinerary passes the validator).

## Why this exists

The owner and their partner are the only users. Two wishes came out of a discussion:

1. **Multi-city trips the user designs**, for example Tokyo, then Kyoto, then Osaka, with the
   cities and their order chosen by the user. Today an area trip picks base cities itself and
   joins them with driving legs (ADR 016), and Japan areas are refused on purpose
   (`area_single_city_only`, `single_city_countries`) because rail, not driving, links Japanese
   cities.
2. **Photos that work without anyone running a GitHub workflow.** In the installed APK the owner
   sees no attraction photos and cannot choose a destination photo.

Opening the app to every country and city (on-demand region loading) is **deliberately left open
for now**. Do not build it. Loading a city may take a while; that is acceptable later.

## Part 0: find out why the APK shows no photos (do this first, report before building)

Photos are served by the backend from Supabase Storage; the APK contains none. ADR 022 step 3
(covers, place detail, credits) is merged. Check, on the real deployment, with a trip to an
Austrian city:

- does `GET /v1/trips` return `cover_image` and does an itinerary item return `image`;
- does `GET /v1/images/{id}` return a JPEG (Storage key works with the new `sb_secret_...` key?);
- is the owner's APK newer than commits `28c5817` and `893a133`;
- the Supabase project may have been paused (ADR 005).

Report what you find. Fix a real fault before adding features.

## Part 1: explicit multi-city trips (new ADR 024)

### Idea

A trip gets an ordered list of **stops** (city, number of days). Each stop is planned like a
single-city trip; the legs between stops are transport blocks. Most of the machinery exists: area
trips already have per-day base cities, `arrival_*` legs on `app.itinerary_day`, transport
markers in the app, and the Phase 7 recalculation works per day. The main change is that the
bases and their order come from the user, not from `planner/areas.py` (`eligible_bases` and the
allocation of days are skipped; the user's list replaces them). Verify this reuse in the code
before committing to it.

### Decisions the ADR must make (propose a default for each, ask the owner where marked)

1. **Data model.** New `app` table, e.g. `app.trip_stop` (trip, position, city reference by
   GeoNames id, snapshot of name and coordinates, days). No foreign key into `geo`. Next
   migration number after `0010`. A trip's `destination_kind` gains a value (for example
   `route`); decide whether a single-destination trip stays as it is (recommended: yes, no change
   for existing trips). The destination stays fixed after creation unless you decide otherwise;
   say so.
2. **Days.** The stops' days add up to the trip length. Default split is even; the user can
   change it. Validate in the API.
3. **Order.** User-defined, never reordered by the planner. Optionally show the driving
   distance between consecutive stops as information.
4. **Legs between stops, and the Japan rule (owner decision).** Rule 5 forbids invented travel
   times. Options: (a) driving legs through the existing travel-time service where driving is
   sensible; (b) for countries in `single_city_countries` (Japan), a leg labelled "by train, time
   not calculated" with a fixed, configured, clearly labelled estimate block in the day's budget
   (the existing estimate fallback is already labelled); (c) wait for Phase 10 (public
   transport). Recommend (a) plus (b), with the label visible in the app, and lift the Japan
   refusal only for explicit stops, not for areas. Ask the owner to confirm.
5. **Regions.** Every stop must be in an `available` region (ADR 009). Otherwise
   `region_not_available`. Japan must be imported before it can be used; check the quality gate
   (gate 5, names without Latin letters) and what the planner does about it. If it does not pass,
   say what a display rule would need and ask the owner.
6. **API.** Create trip with stops; read them on `Trip`; the generation endpoint plans per stop;
   `422` reasons for an unavailable stop. Update `openapi.json` (`python
   scripts/export_openapi.py`, then `npm run generate`).
7. **Planner.** Bump `CONFIG_VERSION`, keep two meaningfully different proposals (diversity gate
   for route trips: they differ in the visits of each stop, since the bases are fixed), update
   golden files with `--update-golden` and review the diff, extend the independent validator
   (stops in order, days add up, legs present, base city per day), new reason codes and
   templates only through the fixed template table.
7b. **Recalculation.** Adding a place or restaurant must pick the right stop's days
   (`place-suggestions`, `recalc.add_place` `only_day`), and removing or locking works as today.
   Test with a 3-stop trip.
8. **Mobile.** Create-trip screen: "Add another city" (destination search per stop), reorder,
   days per stop, total length shown. Overview and Itinerary show the city of each day and the
   transport markers between cities (existing markers). Trip card name for a route trip: decide
   (for example "Tokyo to Osaka"; cards show only name, dates and length, ADR 021). Cover: the
   first stop's photo unless the user chose one.
9. **Tests.** Engine golden tests, validator tests, API tests, app component tests, all on
   synthetic fixtures (state this in the docs, as earlier phases do). No test calls a public
   server.
10. **Docs in the same change:** the ADR, `docs/architecture.md` (planning and API sections),
    `docs/data-model.md`, `docs/app-plan.md`, `docs/design.md`, `CLAUDE.md` (current state).

## Part 2: photos (amend ADR 022; read the new terms first)

### 2a. Better coverage for cities, regions and countries

Measured on Austria: cities 35% (7 of 20), attractions 76% (an upper bound). Areas have none
because `geo.admin_area` does not keep a Wikidata item.

- **Fallback chain for cities, regions and countries:** Wikidata image property, then the
  Wikipedia lead image (page image) of the same Wikidata item (through its sitelink), then the
  item's Commons category. Whatever the step finds must resolve to a **Commons file** and pass
  the unchanged licence allow-list and quality gate (decisions 2 and 3). A local Wikipedia
  upload (not on Commons, often fair use) is rejected. After a rejected candidate, try the next.
- **Terms:** this uses a Wikimedia API not yet read for ADR 022. Read its official terms and
  rate rules, record the date and the finding in the ADR table (rule 4). Same host family,
  same User-Agent, same serial, rate-limited adapter (`adapters/wikimedia.py`).
- **Areas:** keep the `wikidata` tag of admin areas in the import (migration) so a country or
  region trip can have a photo. Existing imported areas need a re-import or a backfill; say
  which.
- **Measure** on at least one region after building (hits, licence mix, share passing the gate)
  and write the numbers in the ADR amendment. If countries and regions are still poor, propose a
  small curated set (hand-picked Commons files with stored licence data) as a follow-up; do not
  build it without the owner.
- **Owner question:** portrait photos caused 16 of 24 attraction rejections. Keep the landscape
  rule (default), or allow portrait on the place detail screen only.

### 2b. "Change photo" with candidates (ADR 022 step 4)

- `GET /v1/destinations/{id}/cover-candidates`: up to 12 candidates (the destination's own
  image, then freely licensed images of its Commons category and the new fallbacks), all passing
  the gate, cached for a week, counted by the daily budget. Returns **small previews fetched by
  the backend**, so the app still calls only the backend.
- Choosing one: download, resize (JPEG, 1,080 px, Pillow), upload to the `photos` bucket, write
  `geo.image`, set `app.trip.cover_image_id`. Available on the new-trip screen and later from the
  trip menu. For a multi-city trip, offer candidates for any of its stops' cities.
- "Image credits" list under More (decision 20): author, licence, link for every image shown.
- Day thumbnails with a photo of the day's first sight (decision 19) are optional; do them only
  if cheap.

### 2c. Automatic loading, no GitHub workflow (answer: yes, for photos)

The resolver runs on the API, not in a workflow:

- **Trigger:** when a destination (each stop) is chosen, when a trip is created, and after
  itineraries are generated, enqueue a **background resolve** for the trip's cities and the
  planned places that have no photo and are not marked `none` (ADR 022 decisions 13 and 14).
  The response returns immediately. The app shows the illustration until the photo exists and
  refreshes on focus or pull-to-refresh.
- **It must survive Render Free**: 512 MB RAM, spin-down when idle, restarts at any time.
  Therefore the job is idempotent and resumable from `geo.image_lookup` (every outcome is
  already recorded), single-flight (a Postgres advisory lock, so two requests never run two
  resolvers), self-healing (a later trips read finds unresolved places and starts it again), one
  image in memory at a time, download size capped, and it stays inside the serial, one request a
  second, `maxlag`, `Retry-After`, daily budget and 4,000-image rules.
- **Not changed:** the "Resolve images" workflow stays as an operator tool.
- **What does not move to the app:** loading a region's **places** (`osm2pgsql`, 2 GB
  downloads) still cannot run on Render Free and stays an "Import region" workflow for now. Say
  this plainly in the ADR so nobody expects the app to load new countries.
- Check the Supabase service key and bucket (`photos`, public, JPEG, 2 MB) are set in Render.

## Suggested order and acceptance

1. Part 0 diagnosis and report.
2. ADR 024 and the ADR 022 amendment (proposed), with the owner's answers to the marked
   questions. Wait for approval before code.
3. Photos 2a to 2c (smaller, unblocks what the owner sees), then Part 1.
4. Each step on its own branch and PR, tests and CI green (`npm run typecheck`, `lint`, `test`;
   `ruff`, `mypy`, `pytest`; `tools/check_dependencies.py`), docs updated, then "awaits
   acceptance" in `CLAUDE.md`. Do not start the next phase or anything outside this brief.

## Questions for the owner (collect answers in the ADR)

- Leg between Japanese cities: labelled rail estimate now, or wait for public transport?
- Portrait photos on the place detail screen: yes or no?
- Name of a route trip on the card: "Tokyo to Osaka", or the first city?
- May a trip's stops be edited after creation (add, remove, reorder), or fixed like the
  destination today?
