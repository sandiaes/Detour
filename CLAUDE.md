# CLAUDE.md

Guidance for AI-assisted work in this repository.

## Project

Detour is a cross-platform travel-itinerary planner: Android first, iPhone later. The user
gives a destination or area and a trip length; the app proposes at least two meaningfully
different itineraries and recalculates when the user adds places or restaurants.

## Current state

**Trip settings can change the start date** (2026-11-17, ADR 021 decision 106, owner request; tests only): a calendar under "Trip dates", for entering past trips with future dates first and moving them to the real dates, then marking them as past.

**Explore is removed and the fifth tab is a Map tab** (2026-11-17, ADR 021 decision 101, owner request; built, awaiting acceptance; tests only): a flat world map of the cities of your trips, the logo's orange pin for been and its deep green for going (decision 103), a globe icon in the bottom bar; the bottom bar is Trips, Map, Add, Photos, More.

**Direction change of 2026-11-14 (ADR 026, proposed; all six build steps are built: the planner, the
slot-engine removal, the data step, history and the app changes):** Detour is a **trip manager
and travel history first**. Trips usually start empty; generating itineraries is an optional helper
that now produces **sights only** (`planner-3.0.0`: no restaurants or cafés, one unplanned 90-minute
midday gap per day, a 09:00–20:00 day). Restaurants and cafés are **no longer imported** (importer
rules `2026-11-14.1`; migration `0014` deleted them and dropped `geo.restaurant_profile`, the cuisine
and meal-type columns and `itinerary_item.meal_type`; a stored restaurant stop became the user's own
place) and are added only through Photon or by hand as a user place of kind `restaurant` or `cafe`,
with the user choosing the day and time (default 75 and 45 minutes, *proposed*). The Phase 8 slot
engine (`planner/restaurant_slots.py`, `restaurant-suggestions`, `add_restaurant`) is **removed**.
ADR 009 gates 1 to 3 are retired (4 to 6 keep their numbers). A past trip keeps its day-by-day record (migration `0015`: stops with day,
order, start and length in `app.trip_visit`; the past-trip screen has a Days tab); the new-trip screen
leads with "Start a fresh trip" and "Generate itineraries" is the second button; day lists show
an idle stretch as "Free time". Next, in the owner's order: destinations outside the imported regions (**ADR 027, accepted and built**: a trip to any place found through Photon, the gazetteer or typed by hand is an empty `place` trip, migration `0016`; suggestions are refused for it), then trip export
(**ADR 028, accepted and built**: `GET /v1/trips/{id}/export`, `POST /v1/trips/import`, a `.detour` zip file with optional documents, import as a new place trip with a manual plan; the app has Export trip, Back up all trips and Import a trip), then **Optimize a hand-made trip** (**ADR 029, accepted and built**: `POST /v1/itineraries/{id}/optimize`
and `.../optimize/undo`, a change-set action, migration `0017`; `planner/optimize.py` reorders the user's
stops for the least travel, within or across days, never longer, with a preview and an undo). **Owner's UI review of 2026-11-15** (ADR 021, decisions 68 to 77, built, awaiting acceptance): a stop's
length is editable with a default to go back to (API: `Item.default_duration_minutes`,
`ItemUpdate.use_default_duration`), one free length field and drop-downs on Add a place, Back keeps
the day and stop, a compact Optimize screen, and the Overview tab is the itinerary (no Itinerary
tab; "Start a fresh trip" and "Generate itineraries" on the new-trip screen, no travel style). The build order is in ADR 026; the
paragraphs below were written before this decision, so where they describe meals, meal windows,
cuisines, imported restaurants or the slot engine they are out of date.

**Phase 9 (hardening for the owner's own APK) is under way** (2026-11-15; [`docs/audit-phase-9.md`](docs/audit-phase-9.md),
[`docs/test-plan-phase-9.md`](docs/test-plan-phase-9.md)). The owner wrote "I approve everything from
ADR013 onwards" and that the app is "all wrong" on the phone; no ADR status was changed (the audit
lists what the approval covers). Built: the app reconnects by itself (5 s doubling to 60 s), says
which dependency is down (paused database, photos, Photon, 429), falls back to the illustration when
a photo fails and to "not available" (not "nothing found") when Photon fails; API request limits
(`abuse.py`: per installation, registrations, photos; 429 with Retry-After); the APK no longer
declares location or draw-over-apps permissions and has Android cloud backup off; migration `0020`
(RLS on `public.alembic_version`); the retired meal, cuisine and slot templates are gone (a stored
code without a template is not shown); the daily "Back up app data" workflow; an opt-in project
signing key ("Create signing key" workflow, `plugins/withReleaseSigning.js`); `privacy.md`,
`security.md`, `backups.md`, `android-release.md`, `known-limitations.md`, `ios-readiness.md`; both E2E
flows brought up to date. **Production** (read-only check): migrations `0014` to `0019` have run (at
`0019`), Austria and Italy are available. GitHub Actions stopped starting jobs on 2026-11-15
(the private repository's minutes were used up); the owner then decided to **make the repository
public** (ADR 007 addendum): workflows must never log or upload anything secret or personal (the
backup is always encrypted, the signing key goes straight into secrets). No journey has been checked
on a device (checked by tests only).

**People and shared trips** (2026-11-16, ADR 034, proposed, owner request; all six questions answered, codes
chosen): a person with devices (link codes and a recovery code, no email or sign-in provider), a partner link,
trips owned by a person with members (owner and editor), version checks on every plan write (409 `plan_changed`),
and shared documents (upload toggle on by default), album links and covers in a private Storage bucket behind the
API. **Step 1 is built** (awaiting acceptance; tests only; migration `0024` not yet run in production): `app.person`
whose id is its first installation's id, so `Session.installation_id` is now the caller's person and every query
sees the person's trips from any phone (`Session.device_id` is the phone); `POST /v1/installations/join` with a
one-time link code (8 letters, 10 minutes) or the recovery code (26 letters; signs out the other phones);
`GET /v1/me`, `POST /v1/me/link-codes`, `POST /v1/me/recovery-code`, `DELETE /v1/me/devices/{id}` (401
`device_removed` afterwards); More, Your phones in the app. **Step 2 is built** (tests only; migration `0025` not yet
run in production): `app.trip.owner_person_id`, `app.trip_member` (one owner per trip, a trigger adds it), `user_place`
and `place_name_override` by `person_id`; `Session.person_id`; every trip query authorises by membership; only the
owner deletes a trip (403 `not_trip_owner`). **Step 3 is built** (tests only; migration `0026` not yet run in production):
your name (`PATCH /v1/me`), partner links by one-time invite code (`app.person_link`, `POST /v1/people/link`), "Who's
going" (`TripCreate.share_with`), trip members endpoints (share, stop sharing, leave), `Trip.role` and `Trip.members`;
the app's More, People and "Who's on this trip" in trip settings. **Step 4 is built** (tests only; migration `0027` not
yet run): `If-Match` plan versions on direct item changes (409 `plan_changed`) and trip `updated_at` (409
`trip_changed`), `Itinerary.last_change` from triggers on `detour.person`, "Changed by Ana" and a 60 s refresh on shared
trips. **Step 5 is built** (tests only; migration `0028` not yet run; the private `trip-files` bucket exists in
Supabase since 2026-11-16): album links in `app.trip_album` and covers chosen from a phone in `app.trip_file` (JPEG ≤ 1600 px, no EXIF,
base64 in JSON, 250 MB budget) behind `/v1/trips/{id}/albums` and `/own-cover`; the app uploads, downloads and keeps a copy
(`syncTrip`). **Step 6 is built** (tests only; migration `0029` not yet run): shared documents in `app.trip_document` +
`app.trip_file` (kind `document`, kept as uploaded, checked by first bytes, 10 MB, phone-chosen UUID id) behind
`/v1/trips/{id}/documents`; "Upload to the trip" on by default, "Keep on this phone only", "Share them with the trip",
downloads ahead for trips within 14 days, open-on-demand otherwise. All six steps of ADR 034 are built; the iPhone build
is next in the owner's order.

**Regions can be imported from the app** (2026-11-17, ADR 033 step 3, built, awaiting acceptance; tests only; migration
`0023` and the workflow change must reach `main` first; the GitHub token `DETOUR_GITHUB_TOKEN` and
`DETOUR_OWNER_INSTALLATION_IDS` are not set yet): More, Regions lists the catalog (Greater London added) with
Import and Remove for the owner; the backend asks GitHub to run the Import region workflow, which reports progress into
`geo.import_job`.

**Regions can be removed** (2026-11-17, ADR 033 proposed, owner request; step 2 of 3 built, awaiting acceptance; tests only): `DELETE /v1/regions/{id}` (owner only, `DETOUR_OWNER_INSTALLATION_IDS`) with
`GET .../removal-preview` frees a region's imported data and keeps every place and area a trip, a past-trip record or a
name override still names (inactive). Adding a region from the app (dispatching the import workflow) is step 3, not
built.

**Past trips are read-only and can be reopened** (2026-11-17, ADR 006 amendment, owner request; built, awaiting
acceptance; tests only; migration `0022` not yet run in production): every change to a past trip's plan, stays,
cities, dates, name or cover is refused with 409 `trip_past`; `POST /v1/trips/{id}/reopen` makes it active again
and the two-day rule then leaves it alone (`reopened_at`); documents and photo links (phone only) stay open; the
new-trip screen warns about a start date in the past. This replaces "as editable as any other" below.

**Past trips keep their plan** (2026-11-16, ADR 006 amendment, owner request; built, awaiting acceptance;
tests only): marking a trip as past, or the two-day rule, now only sets its status; the plan, routes, stays and
documents stay and the trip is as editable as any other (the `trip_archived` refusals are gone). Undo history is
capped at 5 versions for a past trip (`MAX_VERSIONS_PAST`; 30 otherwise), pruned when it becomes past. No
`app.trip_visit` rows are written any more; trips archived earlier keep theirs and the old past-trip screen
(`archiveOnly` in the app). Export and import carry a past trip's plan.

**Manual transport legs** (2026-11-16, ADR 032, accepted, built, awaiting acceptance; checked by tests
only, not on a device; migration `0021` not yet run in production): a train, bus, metro or tram, ferry,
taxi, walk or other leg the user enters by hand (from and to picked from the trip or typed, day, start,
length or arrival time, or "not known", note), stored as an itinerary item of type `transport` with a
`transport` jsonb value. It is locked; Optimize never moves it or a stop across it and uses its length
as the travel of that stretch; a journey leg covers the day's computed arrival (`Arrival.covered_by_item_id`,
including the Japan "time not calculated" row). Add a place's recalculation names a day with a leg
(`TRANSPORT_LEG_DAY`) rather than planning around it. A new leg goes right after its From stop (replacing
the walk from it), else first for a journey, else by time; if it runs into later stops the app offers to
move them all later in the same edit (`shift_later_minutes`; refused past midnight). Without a car Optimize still walks every computed
leg and names the walks over 2 km. The trip file is **version 2** (legs, stays and Car; version 1 still
imports). The dead "Public transport" pill is removed (ADR 021, decision 100). Phase 10 (Transitous or
MOTIS) is not started; a one-leg transit suggestion is recorded as a candidate only (ADR 032, "Later").

**Photos, first step** (2026-11-16, ADR 031, accepted, built, awaiting acceptance; mobile app only,
checked by tests only): Google's Library API no longer lets an app read albums it did not create, so
a trip's Photos tab keeps **links to the user's own albums** (pasted from Google Photos' Share, Copy
link), which open in Google Photos; the Photos screen lists them by trip. "Change photo" has
**Choose from your phone**: the picture is copied into the app's `covers/` folder and shown instead of
the destination photo. Both live on the phone only (SQLite table `trip_extra`); the trip file carries
the links (`albums.json`), not the cover. No Google API, sign-in or permission. Prompt 14's storage
comparison stays open for a later step.

**Owner's UI requests of 2026-11-15** (ADR 021, decisions 92 to 97, built, awaiting acceptance): a Car pill on the new-trip screen (`app.trip.uses_car`, migration `0018`; off means Optimize only walks), a Day drop-down in Edit time, Add a place opening on the open day at its first free time, sight search around each city of a multi-city trip with the open day's city first and distances from it (`domain/searchAnchors.ts`), a pin map on the day's city showing the plan's stops and known sights, no city line above a day's stops, and the stay's morning row centred between hairlines.

**Accommodation is built** (2026-11-15, ADR 030, awaiting acceptance; migration `0019`): a trip has stays, each for a range of days (`app.trip_stay`, `GET/POST/PATCH/DELETE /v1/trips/{id}/stays`), `Day.start` is the morning leg from the stay worked out on read (not stored), Optimize and the generator start each day at its stay (no leg back at night), and the app has "Where you're staying", a house mark on the map and a morning row in the day list. Migration `0019` has run in production (checked 2026-11-15); export does not carry stays.

**A design system is built** (2026-11-15, ADR 021 amendment, decisions 78 to 90; `docs/design-audit.md`,
`docs/design.md`; built and awaiting acceptance, **checked by tests only, not on a device**): one set of
tokens in `theme.ts` and one set of components in `components/ds` that every screen uses (green main
action and selected state, buttons and fields at radius 12, a ConfirmSheet for deleting a trip, marking
it as past and deleting a document, a type scale of 26 to 12, 48 dp touch targets). `styleTokens.test.ts`
fails when a screen writes its own colour, font size, radius, border, spacing number or control height, or a tappable thing without the focus ring; `e2e/screenshot-tour.yaml` (the
"E2E Android" workflow, flow `screenshot-tour`) is written but **not yet run**; `e2e/trip-flow.yaml` is
out of date with the screens. No behaviour, API or data changed.

**Phases 1 to 8 are implemented.** Phase 1: a monorepo with a placeholder mobile app, a FastAPI
service, a generated API client, CI, an Android APK workflow and Render/Supabase deployment
configuration (ADR 010). Phase 2 (ADR 011, ADR 012; `docs/data-model.md`): the `geo` and `app`
schemas, the region import and GeoNames gazetteer commands and the "Import region" workflow, the
data quality report with the ADR 009 gates, destination and place search, the Photon adapter, a
seed trip, and CRUD for trips, user places and itinerary items. No region has been imported into
the real database yet. **Phase 3 is built and awaits acceptance** (ADR 013, proposed): the
travel-time service behind a FOSSGIS Valhalla adapter, with the `geo.travel_time` cache and the
labelled estimate fallback; it has no endpoint of its own and is used by the planner. The owner's
request-shape check is done (`docs/spikes/fossgis-request-shape-check.md`): the fixed 1 x N shape
agrees with the plain route. **Phase 4 is built and awaits acceptance** (ADR 014, proposed): the
planning engine v1 in `detour_api/planner/` (two strategy profiles, heuristic sequencer, category
duration table, diversity gate, independent validator, reason templates) and
`POST /v1/trips/{id}/itineraries/generate`; tried on synthetic fixtures only. **Phase 5 is built
and awaits acceptance** (ADR 015, proposed): the mobile screens in `apps/mobile/src` (trips, create
trip, comparison of two proposals, day list, plan map, selection, on-device read cache, offline and
"waking the server" states); the owner reported on 2026-11-13 that the app works on the phone. The
Android end-to-end workflow (`e2e-android.yml`) runs **by hand only**. **Phase 6 is built and
awaits acceptance** (ADR 016, proposed): meals in fixed windows at imported places to eat
(`planner/meals.py`), area destinations with base cities and inter-city legs (`planner/areas.py`),
Japan single-city only, migration `0006`; tried on synthetic fixtures only. **Phase 7 is built and
awaits acceptance** (ADR 018, proposed): adding a sight, town or pinned place to a planned itinerary
and removing a visit, through persisted change sets (preview with a diff, then apply or discard), a
repair-based recalculation with a stability cost (`planner/recalc.py`), locked items fixed, an
independent revision validator, itinerary versions (migration `0007`; removing the latest addition
restores the previous version), and the app's add-place and preview screens; tried on synthetic
fixtures only. **Phase 8 is built and awaits
acceptance** (ADR 019, proposed): adding a restaurant (search the local data, then Photon through the
backend, then manual entry with a pin or typed coordinates and optional cuisines and meals), up to
three suggested day and meal slots with reasons, the estimated detour and which items move
(`planner/restaurant_slots.py`), placed through the Phase 7 change sets (action `add_restaurant`,
migration `0008`) and the app's add-a-restaurant screen; tried on synthetic fixtures only.
**The past-trips archive is built and awaits
acceptance** (ADR 006, amendment of 2026-11-13): a trip becomes past when the user marks it or two
days after its last day (checked when the trips are read), keeping one `app.trip_visit` snapshot per
city (each once) and attraction and deleting every plan; the app shows it as a map and a list by
city, with no routes or travel times, and the user can clear skipped visits; the archive's size is
reported; tried on synthetic fixtures only. **A trip-centred app is built and
awaits acceptance** (ADR 020, proposed, owner request of 2026-11-13; mobile app only): a trip with a
chosen plan opens on that plan, "Trip settings" offers new proposals and deleting the trip, and the map
and day list tell sights from restaurants and cafés. **A trip-manager redesign is under way** (ADR 021, proposed, owner request
of 2026-11-13, reference screens in `docs/screenshots/`; mobile app only). Steps 1 to 3 of five are
built and await acceptance: design tokens and components (`src/theme.ts`, `src/components/ds/`,
`react-native-svg`), a bottom bar (Trips, Explore, Add, Photos, More; Add is contextual), the trips
list with Upcoming and Past tabs, a Trip Overview around the active itinerary
(`selected_itinerary_id`) with the original proposals in the trip menu, the itinerary a day at a
time with the map and list sharing one selection and transport markers for new base cities (the
API's `Day` gained read-only `base_city_lat`/`lon`), a place detail screen, and (step 4) adding a
place found by search (sights, towns, places to eat), address or pin with up to three suggested days
from the Phase 7 recalculation (`POST /v1/itineraries/{id}/place-suggestions`, `recalc.add_place`'s
`only_day`, `day` on the add-place preview). Of step 5, **documents are built and await
acceptance** (ADR 023, proposed): tickets, bookings, transport and insurance as PDFs or pictures,
linked to the trip, a day, a place or a journey, **kept on the phone only** (`expo-file-system`, a
`trip_document` table in the app's SQLite database; nothing uploaded). Photos (the user's own),
notes wait for the owner (the trip summary and the user's own photos inside Detour are dropped, ADR 021 decision 105). **An amendment of 2026-11-14** (ADR 021, decisions 25 to 31; the design is described in
`docs/design.md`) is built and awaits acceptance: a near-white, flat look with hairlines instead of
cards, trip cards with only name, dates and length (a trip is named after its destination), an
overview without the days figure, first days or notes, an Itinerary tab of days that open the map of
that day, quieter map markers, a new-trip screen with travel style, public transport (the pill was
removed by ADR 032) and "Start with an empty trip", and meals aimed at lunch 13:00 and dinner 20:00 (day window to 22:00). Adding places
to an empty trip (owner request of 2026-11-14) is built and awaits acceptance: an empty (manual) plan cannot be recalculated, so "Add a place" and "Add a restaurant" let the user choose the day, meal and time directly (`POST /v1/itineraries/{id}/days/{n}/items`; `components/ChooseSlot.tsx`), also offered as "Choose day and time" on planned itineraries. **A fourth amendment of 2026-11-14** (ADR 021, decisions 55 to 67) is built and awaits acceptance: a consistency pass over every screen (compact headers, flat past trip, thin outlined buttons, soft edges, travel written into a hairline, a cleaner map key, four document kinds, a drop-down for "Attraction", the wordmark alone on Trips, a launcher icon that fits its mask). **A third amendment of 2026-11-14** (ADR 021, decisions 42 to 54) is built and awaits acceptance: the
logo wordmark on Trips, the trip's name, dates and length on a full-bleed cover, a tighter and clipped
map, stops that only select, compact day pills, Back from Add document to the Documents tab, a
redesigned Add document with cards, slim pills, plan cards on the overview, cards for the proposals,
and a leaner place detail. **A second amendment of 2026-11-14**
(ADR 021, decisions 32 to 41; reference screens 14 to 16) is built and awaits acceptance: no dark band
or text over photos, credits behind a small "i" on every photo, the proposals as two cards with View
details opening the plan's map, day pills under the map, the Itinerary tab with the Overview layout,
kind icons (fork and knife, coffee cup, landmark), a calendar for the start date, a new Documents tab
and Add document flow (with a date and notes), English place names where OpenStreetMap has them and
search by either name (migration `0010` fills places already imported; later imports keep it current), and a planner fix so one sight mapped twice is one stop. Covers are illustrations,
not photos, until ADR 022 (accepted 2026-11-14: Wikimedia Commons photos through Wikidata, stored in
Supabase Storage, a "Change photo" choice on the new-trip screen and an automatic photo otherwise)
has its steps 2 and 3 built and awaiting acceptance (migration `0009`, `adapters/wikimedia.py`, the image
resolver and `python -m detour_api.importer images`, the "Resolve images" workflow run by hand,
`GET /v1/images/{id}`, `Trip.cover_image` and `Item.image`, photos on the trip card, the trip
overview and the place detail with a credit link; the resolver has run on Austria, 114 photos
stored); "Change photo", the automatic photo after a trip is created and the image-credits list are
step 4. **No budgets,
currencies or prices** (ADR 017, accepted 2026-11-13): none in the app, the API or the database;
bringing them back needs a new ADR. The decisions in `docs/app-plan.md`
section 1 are recorded; hosting (D3) is decided in ADR 005, the licence is Apache-2.0 (ADR 007),
and the app is not distributed through app stores (ADR 008). **Approved by the owner on 2026-11-14** (brief `docs/briefs/multi-city-trips-and-photos.md`; Part 0
diagnosis in `docs/spikes/apk-photos-diagnosis.md`): **the ADR 022 amendment is built and awaits acceptance**
(migration `0011`; a fallback chain for city and area photos through English Wikipedia lead images and
Commons categories; portrait photos accepted and cropped to fit on screen; a background resolver on the API
(`images/background.py`, advisory lock, no workflow needed); "Change photo" with up to 12 candidates and
backend previews; "Image credits" under More; day thumbnails; coverage not yet measured, not checked on a
device). **ADR 024 (multi-city trips) is built and awaits acceptance** (migration
`0012`, `app.trip_stop`; 2 to 6 cities in the user's order with their days; the planner plans each
city and drives between them, legs into or out of Japan have no time; names from a fixed table in
`naming.py`; additions stay near the stops; cities edited through `edit_stops` change sets; the app's
"Add another city" and "Edit cities"; tried on synthetic fixtures only; Japan not imported). **ADR 025
(multilingual place names) is built and awaits acceptance** (owner request of 2026-11-14; migration
`0013`; `detour_api/names/`, described in `docs/multilingual-place-names.md`): one resolver chooses the
English-facing name (the user's override, Wikidata label, English Wikipedia title, OSM `name:en` and
related tags, the source's romanization, safe transliteration labelled "Automatically romanized", the
original) and always keeps the local name; businesses keep their own name; Han, Arabic, Hebrew and Thai
are never transliterated and nothing is translated; Wikidata names are fetched lazily in the background
or by `python -m detour_api.importer names` and cached with a 90-day negative cache; search matches
every name; "Edit display name" on the place screen; not yet run against the production database. Do
not start the next phase until the owner asks for it.

## Read first

| Need | Document |
|---|---|
| What the product does and does not do | `docs/product-brief.md` |
| The current direction (manager and history first) | `docs/decisions/026-trip-manager-first.md` |
| System design and planning engine | `docs/architecture.md` |
| Which providers may be used, and on what terms | `docs/api-evaluation.md` |
| Tables, the licence boundary, lifecycle | `docs/data-model.md` |
| Place names in every language and script | `docs/multilingual-place-names.md` |
| Phases, dependencies, exclusions | `docs/app-plan.md` |
| Targets | `docs/kpis.md` |
| How the app looks and behaves (screens, tokens, patterns) | `docs/design.md` |
| Recorded decisions | `docs/decisions/` |
| Working on the code, CI | `docs/development.md` |
| Deploying | `docs/deployment.md` |
| Building and installing the APK | `docs/android-release.md` |
| Privacy, security, backups | `docs/privacy.md`, `docs/security.md`, `docs/backups.md` |
| Phase 9 audit, journeys, what the owner must check | `docs/audit-phase-9.md`, `docs/test-plan-phase-9.md` |

## Hard constraints

1. **No LLM or generative-AI dependency** in the app, the backend, or any build step that
   produces user-facing content. Explanations are reason codes rendered through fixed templates.
2. **Out of scope, always:** booking, payments, hotel availability, flight-price comparison.
3. **No features beyond the stated product goals.** A new feature needs the owner's approval
   and an ADR.
4. **No new external provider without an ADR** that cites its official terms and the date they
   were read. A free trial is not a free tier.
5. **Never invent data.** No fabricated prices, ratings, opening hours or travel times. Missing
   values are stored and shown as unknown; estimates are labelled.

## Architecture rules

- The mobile app calls only the Detour backend and the map tile host. No other third-party
  call from the app.
- All planning logic lives in the backend, so Android and iOS share it.
- Plan generation makes no third-party network calls, with one exception (ADR 004): travel
  times not yet in the cache come from the FOSSGIS Valhalla server through the routing
  adapter. Otherwise it reads the database and the cache.
- Every external provider sits behind an adapter with a fallback, a timeout, caching, a daily
  budget counter and an identifying User-Agent.
- Do not call public community servers (Nominatim, Overpass, FOSSGIS routing,
  `tile.openstreetmap.org`) from code, tests or the app. Their policies do not allow it.
  Exception (ADR 004): backend code may call the FOSSGIS Valhalla server for travel times,
  through the adapter, within its rate rules, never from tests, CI or the app.
- Provider URLs, keys and the map style URL are configuration served by the backend, never
  constants in the app.
- Keep the two database schemas separate: `geo` for imported open data, `app` for user data.
  `app` refers to `geo` by identifier and does not copy its attributes. No foreign key may cross
  the schemas (a test enforces it). Data from different
  sources is stored as separate source records with their licence.
- The planning engine is deterministic: stable ordering, ties broken by identifier, fixed seeds,
  and the engine, configuration and data versions stored on every itinerary.
- Every generated itinerary must pass the independent validator.
- No Android-only native dependency without an ADR. Use Expo config plugins; do not hand-edit
  native projects.

## Planned stack

React Native with Expo and TypeScript; MapLibre React Native; Python with FastAPI; PostgreSQL
with PostGIS; Valhalla (FOSSGIS server per ADR 004, self-hosted only if S3 and the owner say so); Docker Compose for local development. No OR-Tools: spike S5
found the heuristic sequencer sufficient (D7). Exact versions are pinned in Phase 1 and recorded in
`docs/decisions/001-technology-stack.md`.

## Working conventions

- Follow the phases in `docs/app-plan.md`. Keep changes inside the current phase.
- Change a decision by adding or amending an ADR in `docs/decisions/`, numbered in sequence,
  with status, context, decision, alternatives and consequences.
- When a document states a provider quota or term, keep the source link and verification mark.
  Re-check the official page before relying on a figure; do not copy numbers from memory or
  from third-party lists.
- Update the affected documents in the same change as the work that makes them stale.
- Tests accompany every phase: engine golden tests, validator tests, adapter contract tests
  against recorded responses, API tests, app component tests.
- Attribution for OpenStreetMap, GeoNames and the tile provider must remain visible in the app.

## Commands

CI-first: everything below runs in GitHub Actions (`.github/workflows/ci.yml`) and in Claude Code
cloud sessions; nothing needs a local Windows toolchain. Details: `docs/development.md`.

From the repository root (Node 22):

- `npm ci`: install the JavaScript workspaces (`apps/mobile`, `packages/shared`)
- `npm run format:check` / `npm run format`: prettier
- `npm run typecheck`, `npm run lint`, `npm test`: tsc, eslint, jest
- `npm run generate`: regenerate `packages/shared/src/schema.d.ts` from `packages/shared/openapi.json`

From `services/api` (Python 3.13, `pip install -e ".[dev]"`):

- `ruff check . ../../tools` and `ruff format --check . ../../tools`
- `mypy` (strict)
- `pytest`: set `DETOUR_TEST_DATABASE_URL` to run the four database tests (CI always does)
- `python scripts/export_openapi.py`: rewrite `packages/shared/openapi.json`; run it, then
  `npm run generate`, whenever endpoints or models change (CI fails on drift)
- `pytest tests/test_planner_engine.py --update-golden`: rewrite the planner's golden files after
  an intended engine or configuration change (bump `CONFIG_VERSION`), then review the diff

Other:

- `python tools/check_dependencies.py`: fails if an LLM or generative-AI library is listed
- `python -m detour_api.importer region <id>` / `gazetteer <ISO2>...`: the imports (in CI they run
  through the "Import region" workflow; `osm2pgsql` and `osmium-tool` are needed locally)
- `python -m tests.e2e_seed` (from `services/api`): the fixture database for the Android end-to-end
  test (the "E2E Android" workflow, started by hand)
- `python -m detour_api.seed`: build the labelled seed trip from imported data
- `python -m detour_api.importer names [<region>] [--no-network] [--places N]`: search aliases and
  English place names from Wikidata (ADR 025)
- The database tests also need `osm2pgsql` and `osmium` (CI installs them; locally the import
  tests are skipped without them)
- `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build --wait`:
  optional local database and API (`cp .env.example .env` first)
- Android APK: run the "Android APK" workflow by hand (`docs/android-release.md`; signing key in its
  section 5)
- `python scripts/measure_performance.py` (from `services/api`): engine timings of the Phase 9
  performance pass; `pytest tests/test_performance_api.py -s` prints the API's
- Backups: the "Back up app data" workflow (daily, `docs/backups.md`)

Rules for this phase's code: no secrets in the repository (`.env.example` only; secrets live in
Render, Supabase and GitHub settings); pin exact versions; the app reads the map style URL from
`GET /v1/config`, never from a constant.
