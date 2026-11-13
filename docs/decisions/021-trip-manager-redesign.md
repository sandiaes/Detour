# ADR 021: Trip manager redesign, steps 1 and 2 (design system, navigation, trips, trip overview)

- **Status:** **Proposed** on 2026-11-13, at the owner's request. Steps 1 and 2 of five are built
  and tested in the mobile app only; no backend, API or database change. The owner confirms or
  changes the decisions below before step 3 starts.
- **Date:** 2026-11-13
- **Related:** [`020-trip-centred-app.md`](020-trip-centred-app.md) (extended),
  [`015-phase-5-mobile-shell.md`](015-phase-5-mobile-shell.md) (decision 9, design, superseded),
  [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`017-no-budgets-currencies-or-prices.md`](017-no-budgets-currencies-or-prices.md),
  reference screens in [`../screenshots/`](../screenshots/)

## Context

The owner wants Detour to grow from "two proposals to compare" into a personal trip manager and
travel history, and supplied twelve reference screens (`docs/screenshots/`). The request lists
nine screens and five steps:

1. design system and navigation;
2. Trips screen and Trip Overview;
3. itinerary, map and place detail;
4. add place and suggested placement;
5. photos, documents and trip summary.

This ADR covers steps 1 and 2 only, as asked. The itinerary engine, the APIs and the adjustment
flow (change sets, ADR 018 and 019) are untouched. Several things in the reference screens are
not built and are recorded here as references for later (see "Not built" below).

## Decision

### Step 1: design system and navigation

1. **Tokens** (`apps/mobile/src/theme.ts`): warm off-white page (`#f7f4ee`), deep navy text
   (`#14243a`), muted teal primary (`#2b6b64`), restrained orange accent (`#b5511c`) used for
   places to eat on the map and for the few most important actions, rounded cards (20 dp) with a
   hairline border and a soft shadow, type scale, spacing, radii, shadows and icon sizes. Every
   text/background pair, and white on every cover colour, is asserted at WCAG AA in
   `theme.test.ts`. The existing token names are kept, so every existing screen takes the new look
   without being rewritten.
2. **Components** (`apps/mobile/src/components/ds/`): `Icon` (simple line icons drawn for Detour
   on a 24-unit grid, hidden from screen readers), `Cover`, `IconButton`, `Badge`, `Tabs`,
   `StatRow`, `SectionTitle`, `ListRow` and `RowGroup`, `PlannedFeature` (says plainly that a part
   of the design is not built yet) and `Sheet` (a bottom sheet). `Button` gains an icon and the
   `accent` and `ink` variants; `ScreenHeader`'s back control becomes a chevron icon button, still
   named "Back".
3. **New dependency: `react-native-svg` 15.16.0**, the version Expo SDK 58 pins
   (`expo/bundledNativeModules.json`). It draws the icons and the cover illustrations. It is a
   cross-platform native module maintained in the Expo SDK's set, so Android and iOS both work; it
   needs a new APK build (the "Android APK" workflow). No icon font, no image assets.
4. **Bottom navigation: Trips, Explore, Add, Photos, More.** Add is an action, not a screen:
   outside a trip it opens the new-trip form; on a trip's screens (overview, plan, past trip) it
   opens a sheet: Place and Restaurant go to the existing add-place and add-a-restaurant flows
   with the trip's active itinerary (Phase 7 and 8 preview, apply or discard are unchanged);
   Transport, Note and Document are shown as "Coming later". Without a chosen plan, Place and
   Restaurant say "Choose a plan first"; on a past trip they say it cannot be changed. The bar is
   shown on the four root tabs and on a trip's main screens, and hidden on forms (new trip, add
   place, preview, settings), so Back stays the way out of them.
5. **Explore and Photos** are root tabs that say they are planned and not built. **More** lists
   Saved places, Travel preferences, Export trip and Archive trip as "Coming later", and Settings
   (moved here from the old second tab; pushed, with Back).
6. The navigator stays the small React-state stack of ADR 015; the Android back button returns
   from any other root tab to Trips before leaving the app.

### Step 2: Trips and Trip Overview

7. **Trips** has Upcoming, Past and Archived tabs. Upcoming: every trip that is not past, soonest
   first, undated trips after (newest first). Past: trips the backend marks as past (ADR 006),
   most recent first. **Archived is empty and says why:** hiding a trip in an archive needs a new
   field on `app.trip` and an endpoint; it is listed for the "Archive trip" item of More (step 5 or
   later, owner's decision). ADR 006's "archive" (the past-trip snapshot) is shown under Past.
8. **Trip card:** a cover, title, short dates and length, a status badge in words (Planning:
   no plan chosen; Upcoming; In progress: today is within the dates; Past) and a line of cities,
   places and restaurants. The figures come from the active itinerary (distinct base cities, the
   destination for a single-city trip; visits; meals at a place to eat) or, for a past trip, from
   `GET /v1/trips/{id}/archive` (cities and attractions; restaurants are not kept). Nothing is
   shown for a figure that is not known. The reads go through the existing cache, so opening the
   trip afterwards makes no further request.
9. **The active itinerary is `app.trip.selected_itinerary_id`.** It already exists and the
   selection endpoint already sets it, so no field or migration is added and saved trips keep
   their data.
10. **Every trip that is not past opens on its Trip Overview** (`tripOverview` route): a cover with
    Back and a trip menu, the status, dates and destination, then five tabs:
    - *Overview:* the figures (days, cities, places, restaurants), "Your itinerary" (the profile,
      its emphasis and headline facts, buttons to the day list and the map), the first days (from
      today's day during the trip) as a timeline, and a "Notes and reservations" placeholder.
      Without a chosen plan: "Choose a plan", leading to the proposals.
    - *Itinerary:* every day as a timeline; a day opens the existing day list.
    - *Map:* a button per day opening the existing map of that day.
    - *Photos* and *Documents:* say what they will hold and that they are not built.
    Step 3 replaces the Itinerary and Map tabs' hand-off with the redesigned screens (map and day
    list together, marker and item highlighting each other).
11. **The original proposals are in the trip menu** ("Original proposals"; "Proposals" while no
    plan is chosen), next to "Trip settings". Choosing a plan now opens the trip's overview, not
    the plan's day list; getting new proposals opens them above the overview. ADR 020's decision 1
    ("open on the chosen plan") is kept in spirit: the overview is built around that plan.
12. A past trip still opens on its map of visited places (ADR 006); its redesign is the Trip
    Summary of step 5.

### Covers: no invented photos

13. Detour has no image source. The reference screens' destination photography would need a
    provider (for example Wikimedia Commons) with an ADR citing its terms (CLAUDE.md rule 4), or
    the user's own photos (step 5). Until then each destination gets an **illustrated landscape**
    whose colours and hills are chosen from the destination identifier, so a trip always looks the
    same. `Cover` already takes a photo `uri` for later; nothing is fetched today.

## Not built (kept as references for later steps)

| Item from the request or screens | Why not now | Where it goes |
|---|---|---|
| Destination and place photos | No approved image provider; no invented images | ADR for a provider, or user photos (step 5) |
| Photos tab and grid, Google Photos or device photos | Step 5; an integration needs its own ADR | Step 5 |
| Documents (tickets, bookings, insurance) linked to a place, day or leg | Step 5; needs storage and a data model | Step 5 |
| Notes and upcoming reservations on the overview | Needs a data model | Step 5 |
| Transport, Note, Document in Add | Needs data models | Steps 3 to 5 |
| Archived tab contents, Archive trip, Export trip, Saved places, Travel preferences | Need fields, endpoints or decisions | Step 5 or later |
| Explore | Needs a product decision; no new provider without an ADR | Later |
| Planned-versus-actual budget (screen 9), prices on place detail | **Conflicts with ADR 017** (accepted: no budgets, currencies or prices) | Only after a new ADR approved by the owner |
| Ratings, opening hours shown as fact | Never invented (CLAUDE.md rule 5); opening hours are not checked (ADR 003) | Shown only when the data has them |
| Share trip, Delete from More (screen 10) | Sharing is not a stated goal; Delete stays in the trip's settings | Owner's decision |

## Alternatives

| Alternative | Why not |
|---|---|
| `@expo/vector-icons` (icon fonts) | Loads fonts at start-up and ships whole icon sets; a dozen drawn line icons are enough |
| Icons and covers drawn with plain `View`s | Possible for a few shapes, poor for curves; `react-native-svg` is Expo's standard |
| React Navigation with a tab navigator | A native screens module and a second state model; the stack of ADR 015 handles five tabs |
| Fetch counts for every card from a new list endpoint | A backend change for figures the cached plan reads already give |
| A gradient or blank colour instead of an illustrated cover | Reads as missing content; the illustration keeps the reference screens' feel without inventing a photo |

## Consequences

- Owner action: build and install a new APK (new native module).
- The trips list makes one more request per visible trip with a chosen plan (its itinerary) or a
  past trip (its archive figures), once, then served from the cache for 10 minutes and offline.
- Tests: `domain/trips.test.ts`, `components/ds/ds.test.tsx`, `nav/BottomNav.test.tsx`,
  `screens/TripOverview.test.tsx`; the accessibility test covers the new screens, tabs and sheets;
  the trips, proposals, settings and end-to-end flow tests follow the new navigation.
- **Not verified:** the redesign has not been seen on a phone, in a screenshot or with a screen
  reader; the Metro bundle builds, and the tests check labels, roles, states and touch sizes.
  The Maestro end-to-end flow (`apps/mobile/e2e/trip-flow.yaml`) is updated to the new path
  (select, overview, day list, map, back to the list) but has not been run.
