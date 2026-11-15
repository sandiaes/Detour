# Phase 9 audit (2026-11-15)

Stabilisation of Detour for the owner's own use as a sideloaded Android APK (ADR 008), done in a
Claude Code cloud session on branch `claude/quirky-mccarthy-m4w5du`. No new product features. This
document is the audit (task 1 of Prompt 10); the journeys and their results are in
[`test-plan-phase-9.md`](test-plan-phase-9.md), privacy and security in [`privacy.md`](privacy.md) and
[`security.md`](security.md), backups in [`backups.md`](backups.md).

## 1. Verdict

**Not yet ready to call "ready for the owner's own use".** The backend and the app pass every
automated check (section 9), and the fixes below remove the defects found. But three things stand
between this branch and the phone:

1. **GitHub Actions is not starting any job since about 18:16 UTC on 2026-11-15.** Every run (CI,
   the owner's two "Android APK" runs on `main`, and this branch's CI and "E2E Android" runs) fails
   within five seconds with no runner and no log. The most likely cause is that the month's included
   Actions minutes of a private repository (about 2,000, ADR 005) are used up: 197 runs since
   2026-11-12, CI alone about 12 billed minutes a run. **Owner:** open GitHub, Settings, Billing and
   plans, Usage, and check Actions. Until it starts again no new APK can be built, the E2E workflow
   cannot run, and the daily backup (section 7) will not run. **Update, same day:** the owner
   confirmed the limit was hit and decided to make the repository public (free standard runners;
   ADR 007 addendum). The workflows were made safe for public logs and artifacts first.
2. **No device check was possible here.** The owner reports "everything is wrong" on the phone, with
   no detail. The last APK that built (run 26, 17:21 UTC, commit `6df77d0`) is nearly current, so it is
   not an old app against a new API. The defects found and fixed in this phase (section 8) are the ones
   a test or a read of the code could find; what the owner sees needs to be named, screen by screen.
3. **The critical journeys are checked by tests only** (fixture database, fake servers), never on a
   device: see the test plan, every journey marked "needs the owner".

## 2. ADR status: what the owner must accept

The owner wrote on 2026-11-15: *"Btw, I approve everything from ADR013 onwards. I've been trying on my
phone and everything is wrong."* The task says not to change ADR statuses, and the second sentence
says the device behaviour is not right, so **no status was changed**. The table lists what that
approval covers. Once the phone checks pass, the statuses can be set to Accepted in one commit.

| ADR | Status in the file | Built | Tried only on synthetic fixtures | Needs the owner on a phone |
|---|---|---|---|---|
| 013 Travel-time service | Proposed | Yes: FOSSGIS Valhalla adapter, cache, labelled estimates | Adapter tests on recorded responses; the production cache has 342 rows, so it has run for real | That estimated legs are labelled ("Estimated") on the day list |
| 014 Planner v1 | Proposed (frozen helper, ADR 026) | Yes, `planner-3.0.0` | Weights and profiles on synthetic fixtures only | Generate for a real Austrian or Italian city: two plans, sights only |
| 015 Mobile shell | Proposed | Yes | Component tests with a fake server | Offline read, waking banner, retry (changed in this phase) |
| 016 Meals and areas | Proposed; meals superseded by 026 | Areas yes; meals removed | Area fixtures only | An area trip in Austria |
| 018 Add a place, recalculation | Proposed | Yes | Recalc fixtures | Add a sight to a generated plan; preview; undo |
| 019 Add a restaurant | Proposed; slot engine retired by 026 | Only Photon and manual entry remain | Stub Photon | Add a restaurant through Photon and by hand |
| 020 Trip-centred app | Proposed | Yes | Component tests | Opening a trip opens its plan |
| 021 Redesign and amendments 1 to 8 (decisions to 94) | Proposed | Yes, except Explore, Photos, notes, saved places, preferences (shown as "not built") | Component tests, style lint; the screenshot tour has never run | Every screen; the owner's "everything is wrong" belongs here |
| 022 Photos | Accepted; build awaits acceptance | Steps 1 to 4 except what ADR 022 lists as not built | 689 photos stored in production | Covers, credits, Change photo, Image credits |
| 023 Documents on the phone | Proposed | Yes | Fake file module only; the native picker never exercised | Add, open, delete a PDF and a picture |
| 024 Multi-city trips | Approved; build awaits acceptance | Yes | Fixtures; one real 2-city trip exists in production | Add, edit and remove a city |
| 025 Multilingual names | Proposed | Yes | Fixtures; Japan not imported | A non-Latin place (none imported: see test plan j) |
| 026 Manager first | Proposed; all six steps built | Yes | Migrations 0014 and 0015 tested on fixtures; **they have run in production** (below) | Fresh trip, Free time, past trip Days tab |
| 027 Destinations outside the regions | Accepted; build awaits acceptance | Yes | Stub Photon | A trip to a place outside Austria and Italy |
| 028 Export and import | Accepted; build awaits acceptance | Yes | Fake files; the share sheet and "open with" never tried | Export with documents, import on the phone |
| 029 Optimize | Accepted; build awaits acceptance | Yes | Synthetic plans; the owner has applied it six times in production | Preview, apply, undo |
| 030 Stays | Accepted; build awaits acceptance | Yes | Tests; one stay exists in production | The house mark and the morning row |

**Production database (read-only check through the Supabase connector, 2026-11-15):** schema at
migration `0019` (so `0014` to `0019` **have run in production**, through `start.sh` on Render;
the documents that say "not run against the production database" are out of date and are corrected
in this change); regions `austria` and `italy` available (CLAUDE.md said only Austria); 58,793
places, 12,330 cities, 689 photos; one installation, one trip (multi-city, 7 days from 2026-11-17,
a manual plan at version 50 with 26 stops and one stay), no overlapping times, no stop without its
place; database 122 MB of the 500 MB. Provider calls on the busiest day: Wikimedia 924 of 3,000,
FOSSGIS 56 of 1,500, Photon 7 of 300. Nothing was written.

## 3. Leftovers of ADR 017 (money) and ADR 026 (meals, cuisines, slots)

Searched code, API, database migrations, tests and documents for budget, currency, price, meal window,
cuisine, meal type and restaurant slot.

**Removed in this phase:**

- The reason templates of meals and cuisines (`BREAKFAST_WINDOW` to `CUISINE_NOT_SPECIFIED_BY_YOU`),
  the slot templates (`SLOT_*`) and `slot_text`, the slot-engine issue texts (`RESTAURANT_DOES_NOT_SERVE_MEAL`,
  `MEAL_SLOT_TAKEN`, `MEAL_DOES_NOT_FIT`, `NO_SLOT_FITS`, ...), and the notes `NO_MEALS_YET`,
  `MEALS_FROM_MAP_DATA`, `MEALS_NOT_PLANNED`, `MEALS_SKIPPED_FOR_TRAVEL`, `RESTAURANT_ADDED`,
  `MEAL_REPLACED`. Production holds none of these codes (checked). A stored code without a template
  is now **left out** when read; before, it was shown raw (for example "LUNCH_WINDOW").
- `MealType` (two unused definitions), `add_restaurant` in the change-set models (OpenAPI regenerated),
  the "09:00-22:00" text in the API description, Optimize's constant `MEAL_WINDOW_MIN` (renamed
  `RESTAURANT_SHIFT_MIN`: it is ADR 029's 60-minute rule, not a meal window).
- App text: "Detour suggests the best day and meal" (Add sheet, Itinerary), "Pace, interests and
  meals" (More), and the "Mark as past" warning that said **"Meals and restaurants are not kept"**,
  which has been false since ADR 026 (every stop is kept, restaurants included).
- Documents: the "to change, ADR 026" notes in the product brief, design and architecture.

**Kept on purpose (not a leftover):**

| What | Why |
|---|---|
| `geo.currency`, `geo.country.default_currency_code` | GeoNames reference rows, unused; ADR 017 decision 4 keeps them |
| Item type `meal`, `PlanStats.meals` | ADR 026 item 16: the internal type of a restaurant or café stop, and their count |
| Provider "budget" (`photon_daily_budget`, `reserve_call`) | A daily call budget for providers, not money |
| Migrations 0006, 0008, 0014 and their tests | History: they create and then drop the columns; tests assert they are gone |
| Tests that assert absence (`queryByText(/cuisine|price/)`) | They guard the removal |
| ADRs 016, 017, 019, `app-plan.md` phase descriptions, KPIs marked "(removed)" | Recorded history |
| `REPLACED_NOTES` lists `RESTAURANT_ADDED`, `MEAL_REPLACED` | So a recalculation drops those notes from an old plan |

## 4. Provider terms and attribution

| Provider | Attribution in the app | Identification | Quota | Finding |
|---|---|---|---|---|
| OpenFreeMap tiles, OpenMapTiles, OpenStreetMap | Map credit line from `/v1/config`; Settings lists every licence | n/a (the app loads tiles) | none stated | OK |
| GeoNames (CC BY 4.0) | Settings, from `geo.licence` | import workflow User-Agent | n/a | OK |
| Photon | OSM credit (results are OSM data) | `Detour-backend/0.2 (+https://github.com/sandiaes/Detour)` | own budget 300 a day | The contact URL pointed to a private repository (a 404 for outsiders); **resolved by publishing the repository** (2026-11-15) |
| FOSSGIS Valhalla | not required by their rules for a backend | same pattern | 1/s, burst 10, own budget 1,500 a day | Same User-Agent finding |
| Wikimedia (Wikidata, Commons) | photo credit on every photo and "Image credits" | `Detour-bot/0.1 (+...)` | own budget 3,000 a day | Wikimedia's policy asks for contact information; same finding |

Terms were not re-read in this phase (no network to the providers from this session); the dates in
`api-evaluation.md` and the ADRs stand.

## 5. Error handling and resilience (task 2)

| Dependency down | Before | Now |
|---|---|---|
| No network, Render asleep | Red banner, the app waited for the user to press Retry (or to leave and return) | Tries again by itself after 5, 10, 20, 40 s, then every minute; says in plain words why ("No connection…", "did not answer in time…"); saved trips stay readable with "saved N ago" |
| Supabase paused or limited | "The server had a problem" | "The database is paused or unavailable…; saved trips can still be read", with the age of the saved copy |
| FOSSGIS throttled or down | Labelled estimates (ADR 013) | unchanged; the journey test checks every leg is labelled |
| Photon down or budget used | **Add a place said "found nothing"** | Says the wider search or address search is not available, and offers the pin |
| Wikimedia, resolver or photo storage down | **A blank coloured frame with a credit button** | The illustration, no credit |
| Tiles down | "The map could not load…" with Try again; the day list works | unchanged |
| Name resolution down | Cached or local name, never an error (`test_cached_names_are_used_while_wikidata_is_down…`) | unchanged |
| Too many requests (new) | n/a | 429 with Retry-After and a plain message |

**Tile provider switch:** the style URL comes from the backend (`DETOUR_MAP_STYLE_URL`), so a switch
needs no app release, but the PMTiles fallback of D8 has **no host** (no server; ADR 005) and the
rehearsal of the KPI "Provider switch time" was not done. Open for the owner.

The read cache is a cache, not sync: changes need a connection (ADR 015). Network status is learnt
from failed requests and the app returning to the foreground; no network-status library was added
(it would be a new native dependency).

## 6. Privacy and security (task 3)

See [`privacy.md`](privacy.md) and [`security.md`](security.md). Fixed in this phase:

- **The API had no request limits**: anyone with its address could register installations without
  limit and spend the shared Photon and routing budgets. Now: per installation 300 a minute (burst
  150), registrations 20 an hour (burst 10) for the whole service, photos 600 a minute.
- **Location permission:** the APK declared fine and coarse location (from MapLibre) and "draw over
  other apps" (an Expo default) though the app uses neither. They are now removed from the APK
  through `android.blockedPermissions` (checked with `expo config --type introspect`).
- **Android cloud backup** (`allowBackup`) was on, so Google's automatic backup could copy the trip
  documents and the app's database off the phone, against ADR 023's "nothing uploaded". It is off.
  A token the phone can no longer decrypt no longer blocks connecting.
- **Signing:** the APK is signed with the public debug key (ADR 008 said to replace it before real
  use). The build can now sign with the project's own key from GitHub secrets, and a manual
  workflow creates one; switching needs one uninstall, so it is the owner's call when
  ([`android-release.md`](android-release.md)).
- **Supabase security advisor** (read 2026-11-15): one error, `public.alembic_version` open to the
  Data API's roles with RLS off; fixed by migration `0020` (RLS on, grants of `anon` and
  `authenticated` revoked; tried against a database with an `anon` role: refused). One warning,
  `pg_trgm` installed in `public`: left as is (moving it changes the search indexes; low risk while
  nothing uses the Data API). `app` and `geo` are not exposed to the Data API.
- Log leakage: request logs carry the path only; the test that checks this failed in this session
  because a newer HTTP client (`httpx2`) logged full URLs; its loggers are now silenced too.

## 7. Backups (task 4)

Implemented: the "Back up app data" workflow dumps the `app` schema every day at 02:17 UTC
(optionally encrypted), keeps it 30 days, and its restore was rehearsed on a scratch database
([`backups.md`](backups.md)). **It cannot run while Actions is blocked.** Until then the only backup is
"Back up all trips" in the app, which the owner should do before the trip on 2026-11-17.

## 8. Defects found and fixed

| # | Defect | Where | Severity |
|---|---|---|---|
| 1 | Mark-as-past warning said restaurants are not kept (false since ADR 026) | `TripSettingsScreen` | High: could make the owner avoid archiving |
| 2 | No automatic reconnection after a failed start | `BackendProvider` | High on a phone with patchy network |
| 3 | Photon unavailable shown as "found nothing" | `AddPlaceScreen` | Medium |
| 4 | Failed photo left a blank frame and a credit for nothing | `Cover` | Medium |
| 5 | Retired reason codes would be shown raw | `repo/itineraries.py` | Low (none stored in production) |
| 6 | No API request limits | `abuse.py`, `main.py` | High (shared budgets) |
| 7 | Location and draw-over-apps permissions declared | `app.json` | Medium (privacy) |
| 8 | Android cloud backup on | `app.json` | Medium (privacy, restore failure) |
| 9 | A token that cannot be read blocked connecting | `tokenStore.ts` | Low |
| 10 | Messages for paused database, photos, 429 and five other codes | `unwrap.ts` | Low |
| 11 | Stale app text: "best day and meal", "Pace, interests and meals", generator-first empty list | several | Low |
| 12 | `trip-flow.yaml` and the screenshot tour tapped controls that no longer exist ("Plan a trip", `day-row-1`) | `e2e/` | Medium (the E2E check could not pass) |
| 13 | Request-log test failed when `httpx2` is installed | `logging.py` | Low |
| 14 | Migration table open to Supabase's Data API (advisor error) | migration `0020` | Medium |
| 15 | APK signed with the public debug key, no way to use an own key without editing native code | `plugins/withReleaseSigning.js`, two workflows | Medium (opt-in now) |
| 16 | privacy note for deleting an installation: one SQL statement fails while stops use own places | `privacy.md` gives the two-step order (tried) | Low |

## 9. Test coverage and checks run here

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check`, `mypy` (strict, clean virtual environment) | pass |
| `pytest` with PostGIS 16, `osm2pgsql` and `osmium` (all database tests, `DETOUR_REQUIRE_DB_TESTS=1`) | **813 passed, 0 failed** (final run); 94 % line coverage overall, planner modules 96 to 98 % (KPI 85 %) |
| `npm run format:check`, `typecheck`, `lint`, `npm test` | pass; 52 suites, 502 tests |
| `python tools/check_dependencies.py` | pass |
| OpenAPI export and generated client | in step |
| Docker Compose job | not run (no Docker here) |
| E2E Android | **not run**: Actions does not start jobs (section 1) |

## 10. Accessibility and performance

Accessibility: the existing automated checks (`accessibility.test.tsx`, the style lint, 48 dp
targets, focus rings) pass; nothing was checked with TalkBack or on a device. Performance: see the
test plan, section 4; every measured figure is far inside its KPI on this machine, the device figures
(app start, map, list scrolling) need the owner.
