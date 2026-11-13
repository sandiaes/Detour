# ADR 021: Trip manager redesign (design system, navigation, trips, trip overview, itinerary and map, place detail)

- **Status:** **Proposed** on 2026-11-13, at the owner's request. Steps 1 and 2 are built (mobile
  app only). On 2026-11-13 the owner answered the open questions (see "Owner decisions") and asked
  for step 3, then step 4; both are built: see "Step 3" and "Step 4" below. Step 3 adds one
  read-only field pair to the API; step 4 adds an optional `day` to the add-place preview, a
  suggestions endpoint and a day restriction in the recalculation (default behaviour unchanged).
  There is no database change. Step 5 waits for the owner.
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

## Owner decisions (2026-11-13)

1. **No budgets, currencies or prices**, as ADR 017 says: the planned-versus-actual budget and the
   expected and actual restaurant prices from the request are dropped, not deferred.
2. **Photos:** the owner deals with them later; covers stay illustrations.
3. **Archived:** dropped; Past is enough. The Archived tab is removed from the trips list.
4. **Share and Delete in More:** as proposed (no Share; Delete stays in the trip's settings).

## Step 3: itinerary, map and place detail

14. **One day at a time.** A shared view (`components/plan/DayPlan.tsx`) shows a plan a day at a
    time: a day selector (tabs "Day 1, Sat 1 May"), the day's header (date, base city, totals) and
    its stops in time order (time, a numbered disc that matches the map marker, name, "Attraction ·
    2 h" or "Lunch · Restaurant · 1 h", cuisine for meals) with the walk or drive between them and
    its Routed or Estimated tag. It replaces the long list of all days; a day has at most 40 stops,
    so it is plain views, not a virtualised list.
15. **Map and list share one selection.** In map mode the map fills the top and the day's list sits
    in a sheet under it. Tapping a marker selects its stop and scrolls the list to it; tapping a
    stop selects its marker (dark fill, yellow ring, announced as selected) and eases the map to it.
    A chosen stop expands to show its duration basis, the reasons it is in the plan, and Lock and
    Remove (Phase 7, unchanged: removing goes through the preview). The map key (shapes, line
    styles, "not the road path") moved behind a "Map key" button on the map.
16. **Transport markers.** The only transport in a plan is the journey that starts a day at a new
    base city (area trips, ADR 016). It is shown as the day's first row ("To Graz · Drive from
    Vienna · 2 h 20 min · 191 km", Estimated or Routed) and, on the map, as a navy square marker
    with a transport icon at the new base city and a line from the previous one. To place it, the
    API's `Day` gains **`base_city_lat` and `base_city_lon`**: read from `geo.city` by
    `base_city_id` when the plan is read (a join, not a copy; no migration), null when the city is
    not in the gazetteer, in which case no marker is placed and the row still shows the journey.
    Additive: no existing field or endpoint changes. Stations and other transport hubs are not part
    of plans, so they have no markers.
17. **Where it appears.** The trip overview's *Itinerary* tab shows the active itinerary in list
    mode inside the page; its *Map* tab switches the overview to a compact header (back, title,
    menu, tabs) over the map and list. The overview's day timeline and its "Itinerary" and "Map"
    buttons open those tabs at a day. The plan screen (`itinerary` route, reached from the
    proposals) uses the same view, with List and Map, Select, Add a place and Add a restaurant.
18. **Place detail** (`placeDetail` route, from a stop's chevron "Details of …"): an illustrated
    cover with the kind and name; when (day, start and end), duration and what it is based on,
    location (the open data's address, else the town, else the coordinates), and for sights
    "Opening hours: Not checked" (ADR 003); for places to eat the meal, venue type, cuisine ("Cuisine
    not specified" when the data has none) and diet tags from the data; the reasons it is in the
    plan; Locked and "Added by you"; Show on the map (opens the day's map with the stop
    highlighted), Lock and Remove; the data source and licence (`GET /v1/places/{id}`), or "A place
    you added" (`GET /v1/user-places/{id}`). No description, rating, price or opening hours are
    shown because the data has none. Notes, photos, tickets and (for places to eat) reservation
    details are a "not built yet" card.

## Step 4: add place and suggested placement

19. **One search for sights, towns and places to eat.** Add a place searches the imported sights
    and places to eat near the destination, and the gazetteer's towns, as before, plus a "Places to
    eat" group. Choosing a place to eat opens the restaurant flow (Phase 8, ADR 019) with that place
    already chosen, because a restaurant goes into a meal slot, not a visit slot. "Search more
    widely" (Photon through the backend) is unchanged.
20. **Custom places by address or pin.** A new *Address* tab looks an address up through the same
    backend Photon search (`GET /v1/places/search?include_external=true`; no new provider, ADR 012
    terms) and shows each result's street, postcode, town and country; the user can rename it
    ("Town hall square"). *Pin on map* is unchanged. Either is saved as one of the user's places
    (kind `location`) once, even when the user asks again with another length.
21. **Up to three suggested days, from the existing recalculation.** "Find the best day" calls
    the new `POST /v1/itineraries/{id}/place-suggestions` (`PlaceSuggestionRequest`: the place and
    its length). The backend runs the Phase 7 recalculation (`recalc.add_place`, ADR 018) once per
    day with the new `only_day` restriction, validates each result with the independent revision
    validator, and ranks the days by the recalculation's own stability cost (travel, visits moved
    or left out, retimed items; ties to the earlier day). `Revision` now carries that cost. The
    unrestricted recalculation and the cheapest single day give the same plan (tested), so the
    best suggestion is the day the plain preview would have chosen. No routing provider is asked
    (cached times and labelled estimates), nothing is stored, and the response says how many days
    were tried. When no day fits, the planner's issues are shown in its fixed wording.
22. **Each suggestion shows** the day and time, where it sits ("Between St. Stephen's Cathedral and
    Café Ohne Angabe"), the travel it adds labelled routed or estimated, and what else changes: the
    visits left out (first, as a warning), visits that change day, days based in another town, and
    items with a new time. Reasons come from fixed templates over these facts ("Adds the least
    travel of the days that can take it", "Every planned visit stays in the plan", "Leaves out … to
    make room"). The best is chosen already and marked "Best" in words.
23. **Applying.** The chosen day is previewed through the existing change sets: `ChangeSetCreate`
    accepts `day` for `add_place` (only that day is tried; without it, as before, the cheapest).
    The preview screen (Phase 7) shows the full diff with the provider's times; nothing changes
    until the user accepts.
24. **One card for both flows.** `components/ds/SuggestionCard.tsx` shows place days and
    restaurant slots the same way (title, place, travel, what else changes, why).

## Not built (kept as references for later steps)

| Item from the request or screens | Why not now | Where it goes |
|---|---|---|
| Destination and place photos | No approved image provider; no invented images | ADR for a provider, or user photos (step 5) |
| Photos tab and grid, Google Photos or device photos | Step 5; an integration needs its own ADR | Step 5 |
| Documents (tickets, bookings, insurance) linked to a place, day or leg | Step 5; needs storage and a data model | Step 5 |
| Notes and upcoming reservations on the overview | Needs a data model | Step 5 |
| Transport, Note, Document in Add | Needs data models | Steps 3 to 5 |
| Archived tab (removed, owner 2026-11-13), Archive trip, Export trip, Saved places, Travel preferences | Need fields, endpoints or decisions | Step 5 or later |
| Explore | Needs a product decision; no new provider without an ADR | Later |
| Planned-versus-actual budget (screen 9), expected and actual prices on place detail | ADR 017; the owner confirmed on 2026-11-13: not wanted | Dropped |
| A place's description | No description in the data; none is invented | Only with a source that has one |
| Station or airport markers | Plans contain no transport hubs | A later decision |
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
- Step 4 tests: backend `test_api_changes.py` (suggestions rank up to three days and store
  nothing, the best is the plain preview's day, a chosen day is previewed and applied on that day,
  own places need a length, a place already planned says why, request validation) and
  `test_planner_recalc.py` (`only_day` places it on that day; the cheapest day equals the
  unrestricted result at the same cost; a day that cannot take a distant place is explained); app
  `screens/AddPlace.test.tsx` (suggested days with travel and changes, choosing another day, no
  day fits, address search and renaming, places to eat open the restaurant flow, no duplicate
  saved place), `domain/placeSuggestions.test.ts`, and the accessibility test of the add screen.
- Step 3 tests: `components/ItineraryMap.test.tsx` (selection, camera, transport marker and leg),
  `screens/ItineraryScreen.test.tsx` (one day at a time, shared selection, details),
  `screens/PlaceDetail.test.tsx`, `screens/TripOverview.test.tsx` (Itinerary and Map tabs),
  `domain/itinerary.test.ts` (transport points), the accessibility test (place detail, a chosen
  stop, the map key), and the backend's area-plan test (`base_city_lat`/`lon` match `geo.city`).
- Tests: `domain/trips.test.ts`, `components/ds/ds.test.tsx`, `nav/BottomNav.test.tsx`,
  `screens/TripOverview.test.tsx`; the accessibility test covers the new screens, tabs and sheets;
  the trips, proposals, settings and end-to-end flow tests follow the new navigation.
- **Not verified:** the redesign has not been seen on a phone, in a screenshot or with a screen
  reader; the Metro bundle builds, and the tests check labels, roles, states and touch sizes.
  The Maestro end-to-end flow (`apps/mobile/e2e/trip-flow.yaml`) is updated to the new path
  (select, overview, Itinerary tab, Map tab and its key, back to the list) but has not been run.
