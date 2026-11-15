# ADR 021: Trip manager redesign (design system, navigation, trips, trip overview, itinerary and map, place detail)

- **Status:** **Proposed** on 2026-11-13, at the owner's request. Steps 1 and 2 are built (mobile
  app only). On 2026-11-13 the owner answered the open questions (see "Owner decisions") and asked
  for step 3, then step 4; both are built: see "Step 3" and "Step 4" below. Step 3 adds one
  read-only field pair to the API; step 4 adds an optional `day` to the add-place preview, a
  suggestions endpoint and a day restriction in the recalculation (default behaviour unchanged).
  There is no database change. Step 5 waits for the owner. The amendment of 2026-11-14 (flat design,
  new-trip screen, meal times) is below, and a second one of the same day (proposals, documents,
  calendar, English names, duplicate sights).
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
    *Update 2026-11-14:* the image source is accepted in
    [ADR 022](022-destination-and-attraction-photos.md); this decision stands until it is built.

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

## Amendment of 2026-11-14: flat design, trip and itinerary screens, new-trip screen, meal times

Owner feedback after seeing the app (proposed with the rest of this ADR; mobile app, plus one
planner configuration change). The full description of the screens is in
[`../design.md`](../design.md), which is new and is now the design reference.

25. **Flat, near-white look.** The page is `#fcfcfb` (the beige `#f7f4ee` was too yellow). Details
    screens, lists, forms and figures use hairlines, not cards: `Card`, `RowGroup`, `StatRow`,
    `PlannedFeature`, search results, place facts and suggestions lose their boxes, borders and
    shadows. The one card kept is the trip's cover on the Trips screen.
26. **Trips.** A card is the cover, the name, the dates and the length, and nothing else (no footer
    and no counts, so no plan request per card). **A trip is named after its destination** ("Austria"),
    not "Austria, 8 days".
27. **Overview.** The figures are cities, places and restaurants (no days). The first days and the
    notes placeholder are removed. The tabs sit on a sheet whose top corners curve over the cover.
28. **Itinerary and Map.** The Itinerary tab lists the days as a timeline with thumbnails (screen 12;
    it keeps the cover since decision 36). A day opens the Map tab on that day. In the day's view
    the "Day 1, date, visits, meals…" title is removed, stops are hairline rows with smaller type,
    the map takes about a third of the height and the stops the rest.
29. **Map markers** are small flat discs (26 dp, 34 dp when selected) with a 48 dp touch area, and
    the lines are thinner and grey. Shapes and colours still say sight, place to eat and travel.
30. **New trip** follows screen 13: destination, start date, duration, travel style (Relaxed,
    Balanced, Active) and a public-transport switch. Interests, budget and "popular highlights" are
    removed. Travel style and public transport are shown and kept on the screen but **not stored or
    used** (the screen says so); using them needs a trip field and a planner rule, with an ADR.
    Two actions: **Generate itineraries** (as before) and **Start with an empty trip**, which
    creates the trip, an empty manual itinerary (`POST /v1/trips/{id}/itineraries`, existing) and
    chooses it, with no proposals.
31. **Meal times.** Meals are aimed at lunch 13:00 and dinner 20:00: windows lunch 13:00 to 15:00
    and dinner 20:00 to 22:00 (were 12:00 to 14:30 and 18:30 to 21:00); a meal starts at its window's
    start at the earliest. The day window and both profiles end at 22:00 (were 21:00, and 20:30 for
    Essentials). The sightseeing allowance is kept by adding the extra evening to `free_minutes`
    (Essentials 60 to 150, Wider 90 to 150), so days hold as many visits as before and the 60 to 90 %
    utilisation KPI holds. `CONFIG_VERSION` is `2026-11-14.1+…`; the golden files are regenerated.
    Itineraries already stored keep their old times; new and regenerated ones use the new windows.

**Not done, needs the owner:** adding places to an empty trip. The Phase 7 and 8 flows recalculate
planned itineraries and refuse a manual one; a manual add (choose a day, say how long, place by
hand) is a new flow. Until then an empty trip is created and shown but cannot yet be filled from
the app's Add menu.

## Amendment of 2026-11-14 (second): proposals, documents, calendar, English names

Owner feedback of the same day, with three new reference screens: 14 (the two proposals and a day's
map), 15 (the Documents tab) and 16 (Add document), all in [`../screenshots/`](../screenshots/).
Mobile app, plus one importer and search change (migration `0010`) and one planner fix.

32. **No dark band over a photo.** Trip cards and the trip header lose the gradient; text is never
    drawn over a cover. The card shows the cover, then the name, dates and length under it (the
    status badge stays on the photo, on its own pill). The trip header is **the name and the
    dates/days, centred above the photo**; the status and the destination line are removed. The
    place detail's name and kind sit under its photo.
33. **Photo credits behind a small "i"** in the bottom right corner of every photo (`Cover` draws it,
    so no screen can forget it). Pressing it shows "Photo: author, licence, Wikimedia Commons
    (resized)" beside it, and the credit opens the file page. This replaces the credit line under
    the place hero and at the end of the overview (ADR 022, decisions 17 and 18).
34. **Proposals screen (screen 14, left).** "Choose your itinerary": a sentence, the dates and
    length, and the two plans as cards: the cover, a name from fixed templates ("Classic Vienna",
    "Vienna & beyond"; never generated text), "The essentials" / "A wider experience", the profile's
    sentence, places, restaurants and travel time from the plan's own numbers, **View details** and
    **Choose this itinerary**. A "Compare itineraries" row opens the comparison table. The swipe
    list, the side-by-side layout and the "Recommended" badge of the mock are not built: nothing in
    the data says one plan is better, so the badges read "Best-known sights" and "More variety". The
    mock's "1 city" and "Mostly walking" are not shown: a plan summary has no city count or mode.
35. **View details** opens the plan on its **map with the day pills below the map and above the
    stops** (screen 14, right), with "Choose this itinerary" under it. The same pills sit under the
    map of a trip's Map tab. The pills share the width, the chosen one is dark, and the text is
    centred in each, with or without dates. "Add to Day 1" of the mock is not built there (a proposal
    is not edited; Add works on the chosen itinerary).
36. **Itinerary tab = Overview layout.** It keeps the header and the cover photo and lists the days
    below; **only the Map tab** gives its space to the map (decision 28 is amended).
37. **Icons for kinds:** a fork and knife for restaurants, a coffee cup for cafés and a visitor at a
    landmark for attractions (`KindIcon`), beside the kind's word in the day list, the place detail
    and the search results.
38. **Start date on a calendar.** The new-trip screen's start date opens a month calendar (Monday
    first, drawn in JavaScript: the system date picker is a native module that needs an ADR), with
    "Clear the date". Typing a date is gone.
39. **Documents (screens 15 and 16).** The tab shows, when empty, a short explanation and one tile per
    kind that starts adding that kind; otherwise filter chips (All and the five kinds), a sort
    (newest, oldest, title) and rows with a tinted kind tile, title, "Ticket · PDF · 245 kB", the
    document's date (or what it is about), a thumbnail for pictures and a menu (Open, Edit). **Add
    document** is two steps: how to add, then the form (file, type, title, related to, date, notes).
    Documents gain two optional fields, a **date** and **notes** (500 characters), kept in the same
    on-device record (ADR 023); older documents have neither. Not built, and shown as "Coming
    later": take a photo (camera = native module), add a link, create a document without a file.
    **Google Drive** is reached through the phone's file picker, which lists it; the app makes no
    call to Google. "Make available offline" is not shown: every document is already on the phone.
40. **English names.** OpenStreetMap's `name:en` is already imported (`names_i18n`). The plan now
    shows it as the place's name when the source has one, the place detail keeps the local name under
    it, and **search matches the local and the English name** (`geo.place.name_en_norm`, migration
    `0010`, filled by the importer and, for places already imported, by the migration). Where the
    source has no English name the local name stays: nothing is machine-translated (no generative AI,
    CLAUDE.md rule 1) and no new provider is called (Wikidata labels would need an ADR).
41. **One sight, one stop.** OpenStreetMap often maps one attraction twice (a node and an outline)
    under one name, and a plan could visit it twice in a row ("Beyond Recall" in Salzburg).
    `planner/dedupe.py` collapses candidates with the same normalised name within 300 m before
    planning, keeping the best-documented copy.

## Amendment of 2026-11-14 (third): owner's review of the second amendment

Owner request after trying the build, with the overall reference image. Decisions 42 to 54. Mobile
app only; no backend change.

| # | Decision |
|---|---|
| 42 | **Trips header:** the logo's own wordmark (`assets/detour-logo.png`, from `docs/brand/`) replaces the plain word "Detour". |
| 43 | **Trip header on the photo (reverses the "no text over photos" part of decision 32 for this one place):** the cover reaches the top of the screen under the status bar; Back and the menu sit on it; the trip's **name, dates and length** sit on it bottom left, in white. There is no header row above the photo. A soft gradient (top and bottom, clear in the middle) keeps white text and the status bar readable; it is a gradient, not a band. The photo credit's "i" is lifted above the sheet's curve. |
| 44 | **Map tab:** a tighter header (compact Back and menu buttons and tabs, 36 to 40 dp with hit slop for a 48 dp touch); the "i" of the map attribution is lifted above the sheet that curves over the map; the map is clipped to its own area and the header is drawn above it, so markers dragged past the edge never show over the tabs. |
| 45 | **A stop in the list only selects it** and moves the map to it; nothing opens under it. Lock and Remove are on the place's details only. |
| 46 | **Day pills:** 44 dp tall, the stops' own type (day in 14 semibold, date in 13), and never clipped. |
| 47 | **Back from Add document returns to the Documents tab:** the trip's tab is kept in the route, so any screen opened from a tab returns to that tab. |
| 48 | **Add document:** a compact top bar, cards for the ways to add (Upload from device; Take a photo, "Coming later"), the link and "Create a document" options removed. The file is a card (picture or kind tile, name, size, a "Replace file" pill with an icon); document types and "Related to" are slim chips with icons; Title, Date and Notes are boxed one-line fields as in screen 16. |
| 49 | **Pills are slim:** chips and secondary buttons are 36 dp tall with 13 dp text and an optional icon; hit slop keeps the touch at 48 dp. The proposals' "View details" and "Choose this itinerary" use the same compact size. |
| 50 | **Overview, "Your itineraries":** the active plan and, when there is one, the other proposal are cards (small cover, name, what it is, places, restaurants, travel time, a badge "Active" or "Proposal"). The active card opens the Itinerary tab, the proposal opens its map where it can be chosen. The overview reads the trip's proposals once for this. |
| 51 | **Place details:** the labels When, Duration and Location are gone: one quiet line gives the day, time and length, one the address. Opening hours and "Why it is in the plan" are removed. Show on map, Lock, Remove and Add a document are slim icon pills. |
| 52 | **Proposals** are cards (white, hairline, soft shadow) with the cover inside. |
| 53 | Cards are therefore also used for a proposal, a plan on the overview and a way to add a document (decision 33 kept them for trip covers only). |
| 54 | **Not verified on a device:** the full-bleed cover, the clipping of map markers and the status bar colour depend on the phone's rendering; tests cover the structure, labels and touch sizes only. |

## Amendment of 2026-11-14 (fourth): consistency pass over every screen

Owner request: replace the components still in the older, heavier look with the compact, flat
ones, and several specific changes. Decisions 55 to 70. Mobile app only; no backend change.

| # | Decision |
|---|---|
| 55 | **Headers:** screens inside a trip use `CompactHeader` (Back, a one-line title, an icon button on the right). "Trip settings" is an icon button (`settings`), not a round text button, on the plan screen, the proposals and a past trip. `ScreenHeader` (pushed screens) now has a title-size heading (22) and a compact Back; only a root screen's title is display size. |
| 56 | **Outlined buttons** are thin grey-blue outlines with dark text at every size (they were a thick green outline); the text link style (`quiet`) keeps the accent colour. |
| 57 | **Past trip:** a flat page: a header with the settings icon, one summary, **Documents as a hairline row**, **underlined Map and List tabs**, cities and attractions as hairline rows with icons (no tinted box), Skip and Restore as plain text actions. Its map clips its own area and uses the same small flat markers as a plan (cities navy and square-ish with a city icon, attractions teal and round, the chosen one larger); its key is one line. |
| 58 | **Plan screen** (a proposal opened from the overview): the compact header, underlined Map and List tabs, and "Add a place" and "Add a restaurant" as slim pills. |
| 59 | **Overview, "Your itineraries":** only the active plan has a badge ("Active"); another proposal is a plain card with no badge (this replaces the "Proposal" badge of decision 50). The spacing under the figures and between the cards is tighter, the cover is 260 dp and the cards are 56 dp thumbnails with 8 dp padding, so both cards are fully visible when the overview opens. |
| 60 | **Soft edges:** a short fade of the page colour (10 dp) at the top, under the status bar, and (14 dp) above the bottom bar, so scrolled content and the map dissolve instead of being cut by a line. The bottom bar has the page colour, no border and no shadow. The cover of the overview runs under the status bar and has no top fade; the plan screen, which has its own choose bar, has no bottom fade. |
| 61 | **Travel between stops** is written into a hairline: a line, "Walk 3 min 170 m", a line. The labels "Routed" and "Estimated" are gone from the list; the spoken label still says when a time is an estimate. |
| 62 | **Map key:** Attraction, Restaurant or café, Travel to a new base city, and one line for the direct (dashed if estimated) line; every key sits in one 20 dp column. The key button is a 36 dp flat disc with hit slop. |
| 63 | **Documents:** four kinds only, Tickets, Bookings, Transport, Other. Insurance is removed; a document saved under it reads as Other. On the empty tab the four kinds are one row of small tiles with their names, and the illustration is smaller. |
| 64 | **Add document, "Related to":** only Whole trip and Attraction. Attraction opens a **drop-down** of the plan's places; the long list is gone. A document saved earlier about a day or a journey keeps its link, and its chip while it is edited. |
| 65 | **Trips header:** the wordmark alone ("Detour" and the orange dot) on a transparent ground (`assets/detour-wordmark.png`), 34 dp tall, with no mark and no white background (this replaces decision 42). |
| 66 | **Launcher icon:** the Android adaptive icon was cut by the launcher's mask because the artwork filled the whole canvas. The foreground is now the artwork at 69 % of the canvas, inside the safe zone, over a background image (`adaptive-icon-background.png`) made from the artwork's own edge colours, so nothing is cut. `icon.png` is unchanged. |
| 67 | **Not verified on a device:** the fades, the clipping of markers, the icon on a launcher and the status bar depend on the phone; tests cover structure, labels and touch sizes. |
| 68 | **Amendment of 2026-11-14 (fifth), owner request:** (a) a stop row has no hairline of its own, so the travel line is the only divider, and travel reads "Walk · 3 min · 170 m" (this replaces the text of decision 61); (b) a trip card on Trips carries its name, dates and length on the photo, bottom left in white over the cover's gradient, the card 168 dp tall, as screen 01 (this replaces the "nothing over the photo but the badge" rule of decision 36); (c) the Trips wordmark is 31 dp tall, 10 % smaller (replaces 34 dp of decision 65); (d) the lines of a plan card on the overview have fixed heights, so spacing is the same with or without the badge; (e) the place detail has a white sheet with curved top corners over the cover, the name first, then "Kind · Town", then two flat figures (day and date, and "Typical visit"), then the address. |

## Not built (kept as references for later steps)

| Item from the request or screens | Why not now | Where it goes |
|---|---|---|
| Destination and place photos | No approved image provider; no invented images | ADR for a provider, or user photos (step 5) |
| Photos tab and grid, Google Photos or device photos | Step 5; an integration needs its own ADR | Step 5 |
| Documents (tickets, bookings, insurance) linked to a place, day or leg | Built on 2026-11-14, kept on the device: [ADR 023](023-trip-documents-on-the-device.md) | Done (awaits acceptance) |
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

## Amendment of 2026-11-14 (fifth, ADR 026): the manager first (proposed, not built)

[ADR 026](026-trip-manager-first.md) records the owner's decision that the app is a trip manager
and history first. Changes to this ADR: on the new-trip screen "Start with an empty trip" becomes
the dark main button and "Generate itineraries" the outlined "Suggest itineraries"; the meal times
of the first amendment (lunch 13:00, dinner 20:00, the day to 22:00) are superseded, because
generated plans have no meals and the day returns to sightseeing hours; the cuisine and meal lines
of the place detail and the add-restaurant screen go; past trips show their days. Decisions on
photos, documents, multi-city trips and names are unchanged.

## Amendment of 2026-11-15 (sixth): the owner's review of the add, optimize and overview screens

Owner request of 2026-11-15. Mobile app, plus one small API addition (decision 74). Built; awaits
acceptance; not checked on a device.

68. **The length of a stop can be edited.** The place's details have "Edit length": one field
    (minutes, or "1h30"), a pill that goes back to the stop's default, a live check, Save and
    Cancel. A length that runs into the next timed stop is a conflict and cannot be saved (the
    server refuses an overlap); one that leaves less time than the trip to the next stop, or ends
    after the usual end of the day (20:00), is a warning that can be saved. Optimize already lays
    stops out with the lengths the user set (ADR 029 rule 9), so a changed length is used by it.
69. **How long to stay is one free field, not pills.** Add a place and Add a restaurant or café
    use the same field with a pill for "stick to the default" ("Typical length" for a sight, whose
    default the server knows; "Default · 1 h" for others; 75 and 45 minutes for a restaurant and
    a café, *proposed*, ADR 026). The fixed 30 to 180 minute pills are gone.
70. **Add a place is a drop-down screen.** A compact header, slim tabs, and a search box whose
    results open as one rounded list under it with small group headings; choosing one closes the
    list and the field shows only the choice (press it to search again). The day is a drop-down
    too, then the start time and the length as slim boxed fields and one dark compact button.
    The restaurant screen's day and time use the same parts, and so does the attraction picker of
    Add document (one shared `Dropdown`).
71. **Back from a place's details returns to the day and stop the user left.** The Map tab's day
    and selected stop are kept in the route (`tripOverview` gained `day` and `itemId`; the plan
    screen keeps `itemId`), not reset to the first day.
72. **New trip.** The travel-style pills are removed (they did nothing). The buttons read "Start a
    fresh trip" and "Generate itineraries", are the compact size, and the title and subtitle are
    smaller. Public transport stays, still saved for later.
73. **Optimize screen.** A compact header; "within each day" and "across all days" as two slim
    radio rows; "Keep in place" is one row (how many stops are kept) that opens a sheet with the
    list, grouped by day, instead of listing every stop of every day on the screen; the note about
    opening hours is removed from this screen (the preview still shows it).
74. **API.** `Item.default_duration_minutes` (read only: the length "use the default" gives; null
    for a place the user pinned) and `ItemUpdate.use_default_duration` (back to the default and no
    longer marked as set by the user). No database change.
75. **A place's details** run under the status bar like a trip's cover: no fade at the top, and
    Back sits on the photo.
76. **Selected stop in a list** is a soft rounded tint with the same room all around the text:
    the list is 8 dp from the screen edge and each row pads its content by 12 dp.
77. **The Overview tab is the itinerary.** The "Your itineraries" cards are gone (the original
    proposals are in the trip menu, new proposals in Trip settings) and the separate Itinerary
    tab with them; the Overview lists the days as the timeline, under the figures, with Optimize
    when it applies. The figures (cities, places, restaurants) are one line each and take half
    the height.

## Amendment of 2026-11-15 (seventh): small review fixes

Owner review, built: the Overview figures sit between the old stacked and the compact size; the
day thumbnails on the Overview carry no photo credit "i" (`Cover credit={false}`; the place's own
screen keeps it); the new-trip destination results use the shared drop-down list (`DropdownPanel`,
`ChoiceRow`); the map centres on a day's single stop at zoom 14 instead of fitting an empty box;
the four trip tabs fill the full width equally at the same text size.

Further corrections the same day: tabs balanced at both edges, the map's tab line at the same height as the others,
the Overview figures stacked and tighter, and the past trip without its two notes, with a colour per day on the map
and in the Days and List tabs, and a cleaner marker panel.

## Amendment of 2026-11-15 (eighth): the design system (decisions 78 to 90)

A design-consistency audit of every screen (`docs/design-audit.md`) found one app drawn with several
sets of buttons, fields, chips, radii and type sizes. The owner accepted the audit's recommendations
for decisions D1 to D6 on 2026-11-15. The redesign changes how things look and are built, not what the
app does: no screen, route, API or data changed. Status: **built, awaiting acceptance; not checked on a
device or in screenshots**.

78. **Green is the main action and every selected state (D1).** `primary` fills the main button;
    `selected` (the same green) marks tabs, chips, segments, day pills, radios, check boxes, the
    calendar and the bottom bar. Navy (`ink`) stays for text, transport markers and the selected map
    marker. This replaces decision 49's navy main button and the navy day pills, tabs and calendar.
79. **Buttons and fields have radius 12; pills are for chips, badges and filters (D2).** This replaces
    decision 49's pill buttons: an action and a choice now look different. One `Button` has four
    variants (primary, secondary, ghost, destructive) and two sizes (44 and 36 dp).
80. **The page stays `#fcfcfb` (D3).** Decision 25 stands.
81. **Confirmations are a sheet (D4).** Deleting a trip, marking it as past and deleting a document
    ask in a `ConfirmSheet`: a question, one sentence, a red confirming button and a way back. The
    entry buttons are red-outlined. The three inline confirmation blocks are gone.
82. **Touch targets are 48 dp with hit slop (D5).** Drawn controls are 36 to 44 dp; `touchSlop` lifts
    them. A drawn height is a minimum so text can scale.
83. **A screenshot tour (D6).** `apps/mobile/e2e/screenshot-tour.yaml`, started from the "E2E Android"
    workflow with the flow `screenshot-tour`, takes one screenshot of each screen the fixture backend
    can reach and uploads them. Not yet run.
84. **One type scale:** hero 26, title 24, headline 18, cardTitle 16, body 15, label 14, caption 13,
    micro 12. The earlier names (display, heading, small) are gone.
85. **One scale of shape:** radii 6, 8, 12, 16, 24 and pill; borders hairline, 1 and 2; four icon
    sizes (14, 16, 20, 24) with one stroke; control heights 44 and 36, rows 56 and 48; a 16 dp screen
    gutter, 24 between sections.
86. **One set of components** in `components/ds`; the old `ui.tsx`, `Button`, `BoxField`, `Dropdown`
    and the unused `PlanSummaryCard` are deleted. No component has an outer margin; the screen's
    gutter does.
87. **Quiet actions.** "Skip" and "Restore" on a past trip are ghost buttons; "Remove" on a place is
    a red-outlined small button.
88. **Past-trip day colours** moved into `theme.ts` (`dayTones`); three were darkened so white text on
    each reaches 4.5:1.
89. **Behaviour kept.** A disabled row is still announced as a dimmed button with its reason in words;
    "Compare itineraries" is announced as expanded or collapsed; the notes counter is the field's hint
    ("11/500 characters"); the server banner no longer repeats the waking text the Trips screen shows.
    Tests that matched old wording or structure follow the design, not the other way round.
90. **A style lint and approved exceptions.** `styleTokens.test.ts` fails on a colour, font size,
    weight, radius or border width written in a screen or component. The exceptions (the cover
    illustration palette, marker sizes, the attribution text, calendar cells, the wordmark, shapes)
    are listed in `docs/design.md`, "Approved exceptions".

91. **Checked a second time, and the gaps closed.** Every control draws one focus ring (`useFocusRing`,
    `FocusPressable`); the style lint also rejects numeric spacing, control heights and
    hand-written hit slop; the map's failure message and key panel are shared (`MapFailure`,
    `MapPanel`); long titles take two lines; the accessibility test visits the screens that
    decision 81 and the Trip settings sheets added. Components the audit proposed but the build
    does not need (`CoverHeader`, `DateField`, `DayPills`, `CoverCard`, `MapButton`) are not built;
    `docs/design.md`, "Where the build differs from the audit's plan", says why.

92. **Car pill (owner request of 2026-11-15; built, awaiting acceptance).** The new-trip screen has a
    "Getting around" row of two pills, **Car** (on by default) and **Public transport** (saved for
    later, as before). The choice is stored on the trip (`app.trip.uses_car`, migration `0018`;
    `Trip.uses_car`, `TripCreate.uses_car`, `TripUpdate.uses_car`). Without a car, **Optimize** treats
    every leg as a walk, however long (travel times come from the pedestrian profile or the labelled
    estimate); generating and recalculating are unchanged, and a trip file does not carry the flag
    yet (an imported trip has a car).
93. **Edit time also changes the day.** Edit time on a place has a **Day** drop-down (as in Add a
    place) above the start time. The new day is checked like the new time (a clash with a stop there
    blocks Save), and the stop is placed in time order in that day (`ItemUpdate.day_index` with a
    `position`; the API already moved items between days).
94. **Add a place starts where the user is.** Choose day and time (Add a place, Add a restaurant, and
    an empty trip) opens on the day that was open on the map or day list (day 1 when none), and the
    start time is that day's **first free time**: from 09:00, the first gap that fits the stop, else
    after the last stop and the trip from it. Choosing another day updates the time until the user sets
    one. This replaces the fixed 13:00 suggestion for restaurants and cafés.

**Consequences.** Every screen shares its parts, so a change to a button or a field is made once.
Screens that were drawn by hand (Trip settings, Export, Import, Settings, Image credits, the
documents) now look like the rest. The tour and the owner's look on a phone are still owed; until
then the design is checked by tests and typechecking only.
