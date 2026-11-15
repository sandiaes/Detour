# Design-consistency audit (2026-11-15)

Phase 1 of the design-consistency redesign: an audit of every screen, state and shared component
of the mobile app **before** anything is changed. Nothing in `apps/mobile` has been changed by this
document. Implementation waits for the owner's OK and for the decisions in section 11.

- **Read:** `CLAUDE.md`, `docs/design.md`, `docs/architecture.md`, `docs/app-plan.md`, ADR 021 (all
  amendments) and every non-test file in `apps/mobile/src` (23 screens, 27 components, the
  navigator, the theme).
- **Method:** each file read in full; style values, component use and button variants counted with
  `grep`; contrast of the colours in question computed with the WCAG formula.
- **Not done yet:** screenshots. This container has no Android emulator (no `/dev/kvm`) and the app
  has no web target, so the app cannot be rendered here. Section 12 proposes how to get before and
  after screenshots from the "E2E Android" workflow.

Line references are to the files as of commit `6b92d03`.

---

## 1. Summary

The app has a good foundation (one token file, one icon set, a `ds/` folder, accessibility tests
that hold every control to 48 dp and a spoken name), but it was built in eight rounds and each
round added its own versions of the same parts. The result:

| Area | What the code has today | Target |
|---|---|---|
| Text inputs | **6** implementations (`Field`, `BoxField`, `Dropdown` field, Add-document box, the new-trip hairline field, the city-search underline) with heights 40, 44, 48 and ~60, radii 8 and 14, borders 1, 1.5 and a hairline in a colour below 3:1 | 1 field shell, 1 height |
| Buttons | 5 variants (`primary` teal, `ink` navy, `accent` unused, `secondary`, `quiet`), 2 sizes; the screen's main action is navy on 12 screens and teal on 13; **no destructive style** ("Yes, delete the trip" is a teal filled button) | 4 variants with fixed roles, destructive distinct |
| Headers | **6** layouts (`ScreenHeader`, `CompactHeader`, a copy of `CompactHeader` inside the trip overview, the Add-document `FormHeader`, the new-trip header, two cover heroes) with titles at 18, 22, 26 and 30 | 2 headers + 1 cover header |
| Selection | 3 colour systems: navy (tabs, day pills, calendar, photo tabs, radios in Optimize), teal (chips, bottom bar, radios in suggestions), grey tint (stop rows, suggestion cards) | 1 rule |
| Mode switches | underlined `Tabs` (Add a place), `Chip`s (Add a restaurant, "Suggest a day / Choose day and time"), custom pills (Change photo) | Tabs for pages, one segmented control for modes |
| Steppers | 3 (`ui.Stepper`, unused; the new-trip days; the city days), drawn with "−" and "+" characters | 1 |
| Rows | `ListRow`, `ChoiceRow`, the restaurant `ResultRow`, the city-search result, Image-credits rows, the "Compare itineraries" row, the Optimize rows, document rows, past-trip rows, timeline rows; three different "fact" rows | 1 row with documented slots, 1 info row |
| Cards | the `card` token (radius 20, shadow), plus a component called `Card` that is **not** a card (a flat block with a bottom hairline), plus a tinted privacy box, notices and legends at radius 8 and 14 | 1 card, renamed flat section |
| States | `LoadingState`/`EmptyState`/`ErrorState`/`WakingServer` at 22/16 pt, three hand-made empty states, `PlannedFeature`, plain "Searching…" lines in two styles, `Notice`, and `BackendBanner` with raw values | 1 state view, 1 inline status, 1 notice |
| Type | 7 tokens, but 11 literal font sizes, body at 16 for routine labels, card titles at 14, 16, 18 and 22, section titles at 13, 14 and 18 | 8 tokens, body 15 |
| Spacing | gutter 16 nominally, but **32 dp** wherever a padded container holds a `Notice`, a `ListRow` or a timeline row (a margin baked into those components), 8 on the day list, 8 in the compact header | 16 everywhere, components carry no outer margin |
| Radii | tokens 8, 14, 20, pill, and 15 literal radii (2 to 32); sheets curve at 20 in two places and 28 in one | 6 tokens |

Most screens can be brought into line by **replacing parts, not redesigning layouts**: the
information architecture stays.

---

## 2. Screen inventory

Every route of `nav/Navigator.tsx`, every sheet and every state that has its own look. "Look" is
the current generation: **compact** (built in the 2026-11-14 and -15 restyles), **mixed**, or
**older** (spacious, 16 pt body, 48 dp pill buttons, `Card` blocks).

### 2.1 Root tabs and global chrome

| # | Screen / element | File | States and sub-views | Header | Look |
|---|---|---|---|---|---|
| S1 | Trips | `screens/TripsScreen.tsx` | loading, waking, offline error, error, no trips at all, Upcoming, Past, empty tab, offline/refresh notices, pull to refresh, trip card (cover with name, dates, badge) | wordmark | compact |
| S2 | Explore | `screens/ExploreScreen.tsx` | planned feature only | `ScreenHeader` (no back) | mixed |
| S3 | Photos | `screens/PhotosScreen.tsx` | planned feature only | `ScreenHeader` (no back) | mixed |
| S4 | More | `screens/MoreScreen.tsx` | two row groups, disabled "Coming later" rows, a note | `ScreenHeader` (no back) | mixed (double inset) |
| G1 | Bottom bar | `nav/BottomNav.tsx` | four tabs, contextual Add disc | — | compact |
| G2 | Add to this trip (sheet) | `nav/BottomNav.tsx` | rows Place, Restaurant, Transport (disabled), Note (disabled), Document; disabled "Not now" with reason | sheet title | compact |
| G3 | Server banner | `components/BackendBanner.tsx` | connecting, waking, could not reach + Retry | — | older (raw values) |
| G4 | Soft edges | `components/EdgeFade.tsx` | top 10 dp, bottom 14 dp | — | compact |

### 2.2 Creating a trip

| # | Screen / element | File | States and sub-views | Header | Look |
|---|---|---|---|---|---|
| S5 | Create new trip | `screens/CreateTripScreen.tsx` | search idle, "type 2 letters", searching, waking, offline, error, results drop-down, nothing found, "Search more widely" (results / none / unavailable), "Enter it by hand" (latitude, longitude), chosen destination (name, kind, X, cover, Change photo, photo credit), area hint, not-plannable reason, multi-city stop list, start date, duration stepper or route total, public transport switch, cities problem, offline notice, planning notice, problem notice, two main buttons, "Open the trip without a plan" | own (back row + title 22 + subtitle) | mixed |
| M1 | Start date (sheet) | `components/ds/Calendar.tsx` | month grid, today ringed, chosen filled, Clear the date | sheet title | compact |
| M2 | Add a city (sheet) | `components/StopList.tsx` (`CitySearchSheet`) | input, searching, error, none, results, unavailable result | sheet title | older (own input and rows) |
| M3 | Change photo (sheet) | `components/ds/CoverPicker.tsx` | city tabs (multi-city), loading, error, none, 3-across grid with credit, chosen tick, Automatic photo | sheet title | compact |
| C1 | Stop list (multi-city rows) | `components/StopList.tsx` | number disc, name, detail, − days +, up, down, remove, total, Add another city | — | mixed |

### 2.3 A trip

| # | Screen / element | File | States and sub-views | Header | Look |
|---|---|---|---|---|---|
| S6 | Trip overview: cover + Overview tab | `screens/TripOverviewScreen.tsx` | loading / error / waking / not found (with `ScreenHeader` "Trip"), cover hero with Back and menu, sticky tabs on a curved sheet, figures (`StatRow`), Optimize row, day timeline, no plan ("Choose a plan" block), plan loading / offline / error, notices | cover hero | compact (double inset in body) |
| S7 | Trip overview: Map tab | `screens/TripOverviewScreen.tsx` + `components/plan/DayPlan.tsx` + `components/ItineraryMap.tsx` | inline compact header, tabs, map (loading tag, placing stops, empty day, failed + Try again + Show the day list, key button, legend, attribution), day pills, stops (stop row, arrival row, transfer line, free time line, base city line, empty day), map needs a connection | inline copy of `CompactHeader` | compact |
| S8 | Trip overview: Photos tab | `screens/TripOverviewScreen.tsx` | planned feature | cover hero | compact |
| S9 | Trip overview: Documents tab | `components/documents/DocumentList.tsx` | loading line, error notice, empty (illustration, four kind tiles, Add a document, phone-only note), filter chips, "All documents" + Sort, document rows with thumbnail and "…" | cover hero | compact |
| M4 | Trip menu (sheet) | `screens/TripOverviewScreen.tsx` | Original proposals / Proposals, Change photo, Optimize, Undo Optimize, Export trip, Trip settings | sheet title | compact |
| M5 | Sort documents / document "…" menu (sheets) | `components/documents/DocumentList.tsx` | rows | sheet title | compact |
| S10 | Proposals ("Choose your itinerary" / "Original proposals") | `screens/TripScreen.tsx` | loading, not found, plans loading / error, "Not planned yet" block with Plan this trip, kept plan notice, two plan cards (cover, badge, title, tagline, sentence, facts, stale note, View details, Choose), Compare row and table, "You can always adjust", plan notes (collapsible) | `CompactHeader` + intro + date line | mixed |
| S11 | Plan (itinerary) screen | `screens/ItineraryScreen.tsx` | loading / offline / error, compact header with subtitle, Map / List tabs, Add a place and Add a restaurant pills, estimated-travel notice, plan notes, map or list (as S7), bottom choose bar (Choose this itinerary / "✓ Selected" pill) | `CompactHeader` | compact |
| S12 | Place detail | `screens/PlaceDetailScreen.tsx` | loading / error / waking / removed (with `ScreenHeader` "Place"), cover hero, sheet, title 26, local name, "Automatically romanized", Edit display name (+ editor with `Field`, Save, Cancel, Use the usual name), kind line, Locked / Added by you badges, two figures, address line, meal type fact, action pills (Show on map, Edit length, Lock, Remove), length editor (field, Default pill, conflict / check notice, Save, Cancel), documents section, planned feature, data source line | cover hero (Back only) | compact |
| S13 | Optimize | `screens/OptimizeScreen.tsx` | loading / error / empty (not shown here), intro, two radio rows, Keep in place row, problem, Show a shorter order, offline line | `CompactHeader` | compact |
| M6 | Keep in place (sheet) | `screens/OptimizeScreen.tsx` | explanation, stops by day with check boxes and Locked / Document tags, Done | sheet title | compact |
| S14 | Add a place | `screens/AddPlaceScreen.tsx` | Search / Address / Pin on map tabs; search field, searching, error, grouped results, nothing found, search more widely (results / none); address field, Find the address, results, none, name field; pin map with dropped pin, coordinates line, name field, map needs a connection; chosen place field; How long (+ Default pill); Suggest a day / Choose day and time; Find the best day; suggestions (heading, explanation, up to three suggestion cards, Preview this change); no day fits; Choose slot (as C2); problems; offline line | `CompactHeader` | compact |
| S15 | Add a restaurant or café | `screens/AddRestaurantScreen.tsx` | lead, Search / Enter by hand chips; search field, searching, error, "Saved by you" results, nothing found, Search more widely, wider results / none / unavailable, Enter it by hand; manual form: Name, Kind chips, map with pin, Latitude, Longitude; Choose slot (as C2); problems; offline line | `ScreenHeader` | **older** |
| C2 | Choose day and time | `components/ChooseSlot.tsx` | Day drop-down, start time field, length field + Default pill, Add to day N at HH:MM | — | compact |
| S16 | Change preview | `screens/ChangePreviewScreen.tsx` | loading / error / waking, title by action (Add, Remove, A shorter order, Undo Optimize, Change your cities), summary block, travel change, notes (open for Optimize), diff sections with bullets, "Left out" warning, estimated note, problem, Accept / Discard, closed status + Back to the plan | `ScreenHeader` | **older** |
| S17 | Trip settings | `screens/TripSettingsScreen.tsx` | loading / error / not found, offline notice, Your cities block, Proposals block, Mark as past block with inline confirmation, Delete block with inline confirmation | `ScreenHeader` | **older** |
| S18 | Edit cities | `screens/EditStopsScreen.tsx` | loading / not found, stop list, note, cities problem, problem, Preview the change / Save cities | `ScreenHeader` | mixed |
| S19 | Past trip | `screens/PastTripScreen.tsx` | loading / error / waking / not found, compact header, summary, skipped count, Documents and Export rows, notices, Map / Days / List tabs; map (as `PastTripMap`: day colours, panel with the tapped place or day chips, loading, placing, failed); nothing kept; every visit skipped; map needs a connection; Days (day headings with coloured badges, stop rows); List (city rows, visit rows, Skip / Restore actions); no stops by day | `CompactHeader` | compact |
| S20 | Trip documents (past trip) | `screens/TripDocumentsScreen.tsx` | loading / error, `DocumentList` (as S9) | `ScreenHeader` | mixed |
| S21 | Document | `screens/DocumentScreen.tsx` | loading, not found, kind tile + badge, problem, picture preview, facts, Open, Edit, Delete with inline confirmation | `ScreenHeader` (title = document title) | **older** |
| S22 | Add / edit document, step 1 | `screens/DocumentFormScreen.tsx` | loading, trip not found, problem, lead, Upload from device card, Take a photo card ("Coming later"), opening the picker, privacy box | `FormHeader` (copy of `ScreenHeader`) | compact |
| S23 | Add / edit document, step 2 | `screens/DocumentFormScreen.tsx` | file card with Replace file, Document type chips, Title (clear button), Related to chips + Attraction drop-down, Date (calendar), Notes with counter, Save document, phone-only note | `FormHeader` | compact (own field style) |
| S24 | Export trip / Back up all trips | `screens/ExportScreen.tsx` | loading / error, nothing to export, explanation, documents switch block with warning, problem, offline, done notice, Export / Export again | `ScreenHeader` | **older** |
| S25 | Import a trip | `screens/ImportScreen.tsx` | explanation, reading, problem, offline, summary heading, one block per trip, Import, imported notice, not restored warning, Open the trip / Show my trips, Choose a file | `ScreenHeader` | **older** |
| S26 | Settings | `screens/SettingsScreen.tsx` | Connection (address, status, server, installation), Check again, Data credits (links) | `ScreenHeader` | **older** |
| S27 | Image credits | `screens/ImageCreditsScreen.tsx` | intro, none yet, credit rows with external-link icon | `ScreenHeader` | mixed |

### 2.4 Shared parts with their own look

| # | Part | File | Used by |
|---|---|---|---|
| P1 | Plan map | `components/ItineraryMap.tsx` | S7, S11 |
| P2 | Past-trip map | `components/PastTripMap.tsx` | S19 |
| P3 | Map attribution | `components/AttributionBar.tsx` | P1, P2, S14, S15 |
| P4 | Photo cover and credit | `components/ds/Cover.tsx` | S1, S5, S6, S10, S12, timeline |
| P5 | Suggestion card | `components/ds/SuggestionCard.tsx` | S14 |
| P6 | Plan summary card | `components/plan/PlanSummaryCard.tsx` | **nothing (dead code)** |
| P7 | Resource notices | `components/ResourceNotices.tsx` | S1, S6, S10, S11, S19 |

**Total:** 27 screens, 6 sheets, 4 global elements, 2 composite components and 7 shared parts, each
with the states listed. No screen is outside this list (checked against every `case` of
`CurrentScreen` in `App.tsx` and every `<Sheet` and `<Modal` in the source).

---

## 3. Inconsistent components and styles

### 3.1 Buttons (`components/Button.tsx`)

- **Main action colour differs by screen.** Filled `ink` (navy): New trip, Start a fresh trip,
  Choose this itinerary (both places), Find the best day, Preview this change, Add to day N, Show a
  shorter order, Done, Save document, Open, Preview the change / Save cities. Filled `primary`
  (teal): Accept (change preview), Export, Import, Choose a file, Open the trip, Save (display
  name, length), Plan this trip, See the proposals, Try again (`ErrorState`), Retry (banner),
  every `EmptyState` action, **Yes, delete the trip**, **Yes, mark as past**, **Yes, delete it**.
- **Same action, different look.** "Try again": filled teal in `ErrorState`, outlined in `Notice`
  actions, and "Retry" filled teal in the banner. "Save": teal compact (place detail), navy regular
  (document, cities). "Search more widely": compact outlined (new trip, add a place), regular
  outlined (add a restaurant). "Enter it by hand": text button compact (new trip), outlined regular
  (add a restaurant).
- **Main actions at two heights.** The new trip's two main buttons, Find the best day and Preview
  this change are compact (36 dp); Accept, Save document, Save cities, Export and Import are regular
  (48 dp). A screen's main action has no fixed size.
- **No destructive style.** Delete trip and Mark as past are outlined like any other button; their
  confirmations are filled teal, the colour of a positive action (`TripSettingsScreen.tsx:184`,
  `:227`; `DocumentScreen.tsx:139`). "Delete" on a document is a teal text button. Remove (place)
  is an outlined pill. Only `ListRow` has a `danger` prop, and nothing uses it.
- **Shape.** Every button is a pill (`radius.pill`, `Button.tsx:87`); fields are rectangles at 8
  or 14. The brief asks for buttons and fields at 10 to 12.
- **`quiet` colour** is teal in code, "the accent colour" in ADR 021 decision 56.
- **`accent` variant** is never used.
- **States.** Pressed is opacity 0.8, disabled opacity 0.55, both by opacity only; no focused
  state; the label of a disabled button keeps full contrast (good).

### 3.2 Text inputs, search fields, selects and dates

| Implementation | Where | Label | Box | Border | Radius | Text |
|---|---|---|---|---|---|---|
| `Field` (`ui.tsx:454`) | Add a restaurant (×5), display name editor | 14 semibold, text colour | min 48 | 1.5 `outline` | 8 | 16 |
| `BoxField` (`ds/BoxField.tsx:56`) | Add a place, Choose slot, length field | 13 muted | **fixed** 40 | 1 `outline` | 8 | 14 |
| `Dropdown` field (`ds/Dropdown.tsx:150`) | Choose slot, chosen place, document attraction | 13 muted | min 44 | 1 `outline` | 14 | 14 semibold |
| Add-document box (`DocumentFormScreen.tsx:648`) | Title, Date, Notes | 13 **bold**, text colour | min 44 | 1 **`border`** (1.27:1) | 14 | 14 |
| New-trip hairline field (`CreateTripScreen.tsx:787`) | Destination, start date, duration, latitude, longitude | 13 muted | ~60 row, underline | hairline `border` | — | 16 |
| City search (`StopList.tsx:212`) | Add a city sheet | none | 48, underline | hairline `outline` | — | 16 |

Search fields alone come in four forms (hairline with a pin, underline with a magnifier, box with a
magnifier, box without an icon). Date fields come in two (hairline pressable, box pressable).
Error styles exist on `Field` and `BoxField` only.

### 3.3 Chips, pills, filters, tabs and segmented controls

- `Chip` (`ui.tsx:436`): 36 dp, outline border, selected = soft green fill and green border, a
  "✓ " **character** prefixed when there is no icon.
- Change-photo city tabs (`CoverPicker.tsx:174`): their own 36 dp pills, selected = navy fill,
  caption text at regular weight.
- Day pills (`DayPlan.tsx:540`): 44 dp, radius 14 (not a pill), grey fill, selected = navy fill.
- Badge (`primitives.tsx`): about 22 dp, padding-sized.
- "✓ Selected" on the plan screen (`ItineraryScreen.tsx:259`): a text styled as a soft green pill.
- Map status tags: white translucent pills, two opacities (0.94, 0.92).
- **Mode switches:** Add a place uses underlined `Tabs`; Add a restaurant uses `Chip`s for the same
  kind of choice; "Suggest a day / Choose day and time" uses `Chip`s; Itinerary Map/List and Past
  trip Map/Days/List use `Tabs` (one compact, one regular).
- **Radios and checks:** Optimize radio 20 dp, 1.5 border, navy dot (`OptimizeScreen.tsx:263`);
  suggestion radio 24 dp, 2 border, teal fill with a check (`SuggestionCard.tsx:109`); Optimize
  check box 20 dp, radius 6, navy.
- **Selected colour** is navy in tabs, day pills, photo tabs, calendar and Optimize; teal in chips,
  the bottom bar and suggestion radios; a grey tint for stop rows and suggestion cards; soft green
  for drop-down options.

### 3.4 Steppers

Three: `ui.Stepper` (48 dp round, teal outline, **unused**, `ui.tsx:291`), the new trip's
`DaysStepper` (bare "−" and "+" characters at 24 pt, `CreateTripScreen.tsx:627`) and the city days
in `StopList` (32 dp round, outline, `StopList.tsx:287`). The disabled "+" of the city stepper is
drawn in the hairline colour (1.27:1), nearly invisible.

### 3.5 Cards and surfaces

- The `card` token (`theme.ts`): white, radius 20, hairline, soft shadow. Used by the proposal cards
  (padding 8, cover radius 14), the Add-document option cards and file card (padding 12) and the dead
  `PlanSummaryCard`.
- The trip card is a radius-20 cover with no card around it.
- **`Card` in `ui.tsx:387` is not a card:** a flat block with 16 dp vertical padding and a bottom
  hairline (`accent` makes the hairline teal). It holds Trip settings' four sections, "Choose a
  plan", "Not planned yet", the change summary, Export's switch and Import's trip list. The name
  invites misuse.
- Other surfaces: the privacy box (soft green, radius 14), `Notice` (tinted, radius 8), the map
  legend (white, radius 14, shadow), the drop-down list (white, radius 14, hairline).
- **Overlapping sheets:** the trip's tab sheet curves at 28 (`TripOverviewScreen.tsx:633`), the
  place detail sheet and the map's stop sheet at 20; `docs/design.md` says 28.

### 3.6 Headers

| Header | Title | Back | Used by |
|---|---|---|---|
| `ScreenHeader` (`ui.tsx:38`) | 22 bold on its own row under Back | compact, on its own row | More, Explore, Photos, Settings, Image credits, Export, Import, Trip settings, Edit cities, Change preview, Add a restaurant, Document, Trip documents, loading states of trip overview, place detail and document form |
| `CompactHeader` (`ui.tsx:74`) | 18 semibold, one line, beside Back | compact | Proposals, Plan, Optimize, Add a place, Past trip |
| Inline copy (`TripOverviewScreen.tsx:528`) | 18 semibold | compact | Map tab |
| `FormHeader` (`DocumentFormScreen.tsx:490`) | 22 bold under Back (the comment says "centred"; it is not) | compact | Add / edit document |
| New-trip header (`CreateTripScreen.tsx:781`) | 22 bold under Back | **regular 48** | Create new trip |
| Cover heroes | 30 white with text shadow (trip), 26 on the sheet (place) | on the photo | Trip overview, place detail |

The same kind of screen gets different headers: Add a place (compact) and Add a restaurant (large);
Proposals (compact) and Trip settings (large); Document (`ScreenHeader`) and Add document
(`FormHeader`). The back buttons sit 4, 8 and 12 dp from the edge depending on the header.

### 3.7 Typography

Tokens: display 30, title 22, heading 18, body 16, small 14, caption 13, overline 12 (unused).

- **Routine labels at 16:** regular button labels, `Field` text, `ListRow` titles (16 semibold),
  `EmptyState` / `ErrorState` / `WakingServer` text, Trip settings / Export / Import paragraphs,
  document facts, past-trip city and day headings, new-trip inputs.
- **Card titles** at 14 (timeline day, document row, option card), 16 (`ListRow`), 18 (proposal
  card, suggestion card, **restaurant search result**, past-trip summary) and 22 (trip card).
- **Section titles** at 13 bold (Add-document labels), 14 bold (Optimize, Add a place suggestions,
  Add a restaurant labels) and 18 (`SectionTitle`, Change preview, Settings, Import, Compare).
- **Screen titles** at 18, 22, 26 and 30. **Sheet titles** at 22, larger than the compact header.
- **State titles** at 22 (`EmptyState`) and 18 (empty tab on Trips, empty documents, planned
  feature).
- **Weights** 500, 600 and 700 for the same role (tab 500, bottom bar 500, chip 600, button 600,
  row titles 600 or 700).
- Literal font sizes: see 5.2.

### 3.8 Spacing and density

- **Components carry their own outer margin.** `Notice` has `marginHorizontal: 16` (`ui.tsx:411`),
  `ListRow` pads 16, `StatRow` is full width. Inside a container that already pads 16 they end up
  32 dp from the edge and narrower than everything around them: More (`MoreScreen.tsx:79`), the
  overview body (`TripOverviewScreen.tsx:623` + `:693`: the timeline and the Optimize row),
  Add a place, Edit cities, Change preview, Add document, Document, Export, Import, place detail,
  the new trip's search errors, and the Change-photo sheet.
- **Gutters:** 16 on most screens, 8 on the day list (`DayPlan.tsx:557`, with 12 inside each row),
  8 on compact headers, 12 on the place cover's Back, 8 on the trip cover's.
- **Section rhythm:** gaps between blocks of 12 (Trip settings), 16 (place detail, Add document,
  Add a place), 24 (Settings, Proposals) with no rule.
- **Row heights:** 44 (drop-down option), 48 (city result, Optimize rows), 56 (`ListRow`, stop
  row), 64 (document row), ~72 (restaurant result).

### 3.9 Lists, rows and facts

- **Rows** (near-duplicates of one pattern: leading mark, title, detail, trailing control):
  `ListRow`, `ChoiceRow`, the restaurant `ResultRow` (`AddRestaurantScreen.tsx:469`, 18 pt title
  and a "✓ " character), the city-search result, Image-credits rows, the "Compare itineraries" row
  (`TripScreen.tsx:442`, a hand-made `ListRow`), the Optimize radio and check rows, document rows,
  past-trip city and visit rows, timeline day rows.
- **Facts:** `Fact` in place detail (label left at 72 dp, `PlaceDetailScreen.tsx:70`), facts in
  Document (label over value, 13 / 16, `DocumentScreen.tsx:172`), `Fact` in Proposals (icon and
  caption, `TripScreen.tsx:96`), and `MetaLine` (icon and text).
- **Leading marks:** thumbnails at 56 (radius 10 and 14), 40 × 52 (radius 8), 4:3 (radius 8);
  tiles at 32, 36, 44, 48, 56 (radius 12 and 14); discs at 24 (stops, day badges), 26 (cities,
  map), 10 (timeline), 12 (map day key), 14 (legend).

### 3.10 Sheets and confirmations

- One `Sheet` component (good), but its body is the page colour, not `surface`; its title is 22;
  its corners curve at 20; its backdrop colour is a literal.
- **No confirmation modal exists.** Deleting a trip, marking it past and deleting a document use
  an inline block (an error-toned `Notice`, a filled teal button, an outlined button) built by hand
  three times. Removing a place and every plan change go through the Change preview screen
  (consistent, kept).

### 3.11 Loading, empty and error states

- `LoadingState`: large spinner and 16 pt text, centred with `flex: 1`. Also used inside a sheet
  (Change photo) and inside a scroll view (Import), where `flex: 1` centring does not apply.
- Inline progress has no component: "Searching…" (14 muted), "Loading the documents…",
  "Reading the plan…", "Opening the file picker…" (13 muted), "Planning… this usually takes a few
  seconds." (14 muted), plus the "Planning" `Notice` on the new-trip screen.
- `EmptyState` (title 22, text 16, filled teal action) vs the empty Trips tab (18 / 16, no action),
  the empty Documents tab (illustration, 18 / 14, ink button), `PlannedFeature` (icon, 18 / 14,
  badge, hairlines), the empty day ("Nothing is planned on this day." as a 14 pt line, and again as
  a map tag) and Image credits ("No photo has been shown yet.").
- `ErrorState` = `EmptyState` with "Try again". Errors above content are `Notice`s (with an
  outlined 48 dp button inside). The server banner is a third look with raw values.
- Map failures: a `Notice` plus a separate outlined button, both floating over the map.

### 3.12 Navigation

- Bottom bar: active = teal icon, bold teal label and a 3 dp teal bar; labels at a literal 12.
- Underlined tabs: active = navy bold label and a 2.5 dp navy line. Two components that both mean
  "you are here" use two colours.
- The Add disc in the bottom bar is the only teal-filled control apart from the teal buttons.
- Back: three distances from the edge (3.6). Android Back pops the stack (good).

### 3.13 Icons

- One library (`ds/Icon.tsx`, 24-unit grid, one stroke 1.8): good. Exceptions: the Add disc (2.2)
  and the suggestion check (2.4).
- **Sizes in use:** 10, 13, 14, 16, 18, 20, 22, 26, 28, 32, 36, 56 (twelve).
- **Characters used as icons:** "✓" (chips, restaurant results, "✓ Selected"), "▾ ▸" (plan notes),
  "− +" (steppers), "i" (map attribution, while the photo credit uses the `info` icon), "•"
  (bullets in four places).
- The drop-down chevron is a rotated `chevronRight` although `up` and `down` icons exist.

### 3.14 Colour use

- Teal (`primary`) means: sight, primary button, selected chip, bottom-bar selection, text-button
  colour, kind text, "Locked / Added by you" tags, list icons, the stat icons. Too many roles.
- `link` blue appears only in the plan-notes toggle, map attribution and Settings links.
- Day colours for past trips live in `domain/pastTrip.ts` (`DAY_COLORS`), outside the theme, and
  are tinted by string concatenation (`` `${dayColor(...)}1f` ``, `PastTripScreen.tsx:384`).

---

## 4. Duplicated or near-duplicated components

| Pattern | Implementations | Proposal |
|---|---|---|
| Text input | `Field`, `BoxField`, `Dropdown` field, Add-document box, new-trip hairline field, city-search underline | One `FieldShell` (label, box, hint, error) and `TextField`, `SearchField`, `SelectField`, `DateField` on it |
| Header | `ScreenHeader`, `CompactHeader`, overview inline header, `FormHeader`, new-trip header | `ScreenHeader` (large title) and `CompactHeader`; covers keep `CoverHeader` |
| Stepper | `ui.Stepper` (unused), `DaysStepper`, `StopList` steps | One `Stepper` (sizes md, sm) |
| Selected pill | `Chip`, Change-photo tabs, "✓ Selected" text pill | `Chip` only |
| Mode switch | `Tabs` used as a form switch, `Chip`s used as a form switch | `SegmentedControl` |
| Radio / check | Optimize radio, suggestion radio, Optimize check box | `Radio`, `Checkbox` marks inside `ListRow` |
| Row | `ListRow`, `ChoiceRow`, restaurant `ResultRow`, city result, credit row, compare row, Optimize rows | `ListRow` with slots and a `compact` density |
| Fact | place `Fact`, document facts, proposal `Fact`, `MetaLine` | `InfoRow` (label over value) and `MetaLine` |
| Card | `card` token users, `PlanSummaryCard` (dead), privacy box | `Card` (one look); the flat block renamed `Section` |
| Confirmation | three hand-made inline blocks | `ConfirmSheet` (or one `ConfirmPanel`, see 11) |
| State | `LoadingState`, `EmptyState`, `ErrorState`, `WakingServer`, Trips empty tab, Documents empty, `PlannedFeature`, inline progress lines | `StateView` (loading, empty, error, planned, waking) and `InlineStatus` |
| Banner | `Notice`, `BackendBanner` | `Notice` only |
| Icon tile | `KindTile`, option tile, past-trip visit tile | `Tile` |
| Number disc | stop disc, city number, day badge, map dot, legend key | `StopMark` (list) shared with markers' sizes |
| Map overlay | loading tags ×2, key button, legend, failure, past-map panel close | `MapChip`, `MapButton`, `MapPanel` |
| Dead code | `PlanSummaryCard`, `ui.Stepper`, `type.overline`, `Button` `accent`, unused style keys in `TripOverviewScreen` (`planHead`, `actions`, `chips`, `meta`) and `CreateTripScreen` (`error`, `reason`, `pressed`) | Remove |

---

## 5. Hardcoded values

Counted in non-test `.tsx` files.

### 5.1 Colours outside `theme.ts`

| Value | Where | Proposal |
|---|---|---|
| `rgba(255,255,255,0.94)`, `0.92`, `0.9` ×2 | map tags (`ItineraryMap`, `PastTripMap`), attribution bar and its "i" | `colors.mapOverlay` |
| `#666666` | attribution "i" border (`AttributionBar.tsx:109`) | `colors.outline` |
| `rgba(20, 36, 58, 0.35)` | sheet backdrop | `colors.backdrop` |
| `rgba(20, 36, 58, 0.72)`, `0.86` | photo credit button and bubble | `colors.imageButton` / `colors.imageOverlay` |
| `rgba(13, 24, 40, 0.55)` | hero text shadow (`TripOverviewScreen.tsx:634`) | `textOnImage` token (shared with the trip card) |
| `#0d1828` ×4 | cover scrim gradient (`Cover.tsx`) | `colors.scrim` |
| `` `${dayColor}1f` `` | past-trip row tint | `dayTones` in `theme.ts` with explicit soft colours |
| `DAY_COLORS` (8 hex) | `domain/pastTrip.ts` | move to `theme.ts`, contrast-tested |
| Cover illustration tones (25 hex) | `Cover.tsx` | **exception**: an illustration palette, tested in `theme.test.ts` |

### 5.2 Font sizes outside the type scale

`ItineraryMap.tsx:330` (12), `DayPlan.tsx:605` (12), `Button.tsx:101` (13), `ui.tsx:449` (13),
`ui.tsx:481` (24), `AttributionBar.tsx:97` (12), `AttributionBar.tsx:111` (16),
`BottomNav.tsx:174` (12), `BackendBanner.tsx:36` (14), `CreateTripScreen.tsx:843` (24),
`PlaceDetailScreen.tsx:578` (26). All map to the proposed scale (section 9.2).

### 5.3 Radii, sizes, borders, spacing

- **Radii:** 33 literal values: 2, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 18, 20, 32 and
  half-sizes of discs; plus `SHEET_RADIUS = 28`. Tokens in use: 8, 14, 20, pill.
- **Heights and widths:** 106 literal values; the ones that are component heights repeat: 36 (×9),
  44 (×6), 48 (×7), 40 (×4), 24, 28, 32.
- **Borders:** widths 1 (×12), 1.5 (×5), 2 (×4), 2.5 (tab line), 3 (×2, pins), plus hairlines.
- **Spacing:** 24 literal values outside the scale (gaps 1, 2, 6; paddings 4, 6, 12; margins 2, 6).
- **Banner:** `BackendBanner` uses `padding: 12, gap: 8, fontSize: 14` with no tokens.

---

## 6. Outdated-looking screens

Spacious, 16 pt routine text, 48 dp pill buttons, stacked `Card` blocks, large headers:

1. **Trip settings** (S17): four stacked blocks of 16 pt paragraphs, each with a full 48 dp pill; teal
   destructive confirmations. The heaviest screen.
2. **Add a restaurant or café** (S15): the old `Field`, chips as a mode switch, 18 pt result titles,
   regular buttons, a large header; the sibling Add a place is compact.
3. **Change preview** (S16): large header, a teal-rule summary block, bullet lists, 48 dp buttons.
4. **Export** and **Import** (S24, S25): 16 pt paragraphs, `Card` blocks, regular teal buttons.
5. **Settings** (S26): a text dump ("Address: …", "Status: …") and a regular outlined button.
6. **Document** (S21): large header with the document's title, 16 pt facts, 48 dp buttons, inline
   teal delete confirmation.
7. **State screens**: `EmptyState`, `ErrorState`, `WakingServer` (22 / 16 pt, large spinner) and
   the server banner.
8. Smaller leftovers in compact screens: the "Choose a plan" and "Not planned yet" blocks (S6, S10),
   the new trip's large Back button and 16 pt inputs (S5), the Add-a-city sheet (M2), More's
   double inset (S4).

---

## 7. Accessibility issues

| # | Issue | Where | Severity |
|---|---|---|---|
| A1 | Destructive confirmations look like positive actions (teal fill); only the words differ | Trip settings, Document | High |
| A2 | Input boxes outlined in `border` (`#e4e4e1`, 1.27:1 on white) — a control boundary must be 3:1 (WCAG 1.4.11) | Add document Title, Date, Notes | High |
| A3 | White 13 pt bold text on day colours `#d9772b` (3.17:1), `#7a8b2a` (3.78:1) and `#1f8fa3` (3.81:1): below 4.5:1 | Past trip Days badges | High |
| A4 | Fixed heights that clip at large font scales: `BoxField` 40, day pills 44, compact icon buttons 36, calendar days 40, number discs (only two of them cap the font scale) | Add a place, Choose slot, maps, calendar | Medium |
| A5 | One-line truncation of titles and tab labels (`numberOfLines={1}`): long names or translated labels ("Dokumente", "Übersicht") are cut in the four equal trip tabs and compact headers | Trip tabs, headers, trip cards | Medium |
| A6 | The disabled "+" of the city stepper is drawn at 1.27:1, nearly invisible | Stop list | Medium |
| A7 | White text on a photo: the trip hero has a text shadow, the trip card has none, so its contrast depends on the photo | Trips | Medium |
| A8 | No focus state for keyboard, D-pad or switch access; pressed and disabled are opacity only | All controls | Low (Android phones) |
| A9 | Characters as icons ("✓", "▾", "−", "+", "i") are read aloud by some screen readers where the control has no label of its own | Chips, plan notes, steppers | Low |
| A10 | Selection shown in three colour systems (3.3) makes "selected" harder to learn; the word or state is announced, so it is not a failure | Throughout | Low |
| A11 | Keyboard: no screen uses keyboard avoidance; forms rely on Android's resize mode, which edge-to-edge (RN 0.88) can defeat; the city-search and display-name inputs sit in sheets and cards near the bottom | Sheets with inputs, place detail | Unverified on a device |
| A12 | 48 dp touch targets are enforced by `accessibility.test.tsx` (height plus hit slop): **good**, keep | — | — |

---

## 8. What works and stays

The near-white page, navy text, teal for sights and orange for places to eat; the one icon set;
hairline rows instead of boxes for lists; the cover heroes; the day timeline; the stop rows with
travel written into the hairline; `StatRow`; `Tabs`; `Sheet`; the soft edges; every accessibility
behaviour of the current components (spoken names, states in words, announced headers, 48 dp
targets). The redesign reuses these and changes their details only where this audit lists a
reason.

---

## 9. Proposed design system

Final values are proposed here and confirmed in phase 2; where they depend on a decision in section
11, the recommended option is shown.

### 9.1 Colours

Unchanged: `background #fcfcfb`, `surface`, `surfaceMuted`, `text`, `muted`, `border`, `outline`,
`primary #2b6b64`, `eat` / `accent #b5511c`, `accentText`, `ink`, `warning*`, `error*`.

New or renamed (each contrast-tested in `theme.test.ts`):

| Token | Value | Use |
|---|---|---|
| `primaryPressed` | `#225650` | pressed fill of a primary button |
| `danger` | `#b42318` (white text 6.5:1) | destructive buttons, danger rows |
| `dangerSoft` | `#fbe6e3` (= `error`) | destructive confirmation panel |
| `selected` | = `primary` (recommended, decision D1) | every selected state: tabs, chips, segments, day pills, radios, checks, calendar, bottom bar |
| `selectedSoft` | = `primarySoft` | selected rows and options |
| `backdrop` | `rgba(20,36,58,0.35)` | behind sheets |
| `mapOverlay` | `rgba(255,255,255,0.94)` | tags, attribution and buttons on a map |
| `imageOverlay` / `imageButton` | `rgba(20,36,58,0.86)` / `0.55` | controls and credits on photos |
| `scrim` | `#0d1828` | cover gradient |
| `dayColors` + `dayTones` | the eight day colours, three darkened to reach 4.5:1 with white (`#b35f1d`, `#5f6d1f`, `#18707f`), each with a soft tone | past trips |
| `focus` | `primary`, 2 dp ring | focused controls |

### 9.2 Typography

| Token | Size / line | Weight | Role |
|---|---|---|---|
| `hero` | 26 / 32 | 700 | the name on a trip or place cover |
| `title` | 24 / 30 | 700 | screen title (`ScreenHeader`) |
| `headline` | 18 / 24 | 600 | section title, compact header title, sheet title, state title |
| `cardTitle` | 16 / 22 | 600 | a card's or a primary row's title (proposal, menu row); a trip card's name on its photo uses `headline` at 700 |
| `body` | 15 / 21 | 400 | paragraphs, input text, regular button labels (600) |
| `label` | 14 / 20 | 500–600 | list titles (stops, choices, documents), compact button labels, field values |
| `caption` | 13 / 18 | 400–500 | metadata, field labels, hints, chips |
| `micro` | 12 / 16 | 500–600 | bottom-bar labels, badges, map attribution |

### 9.3 Spacing, layout and sizes

- **Spacing scale** (unchanged): 2, 4, 8, 12, 16, 24, 32. **Rules:** screen gutter 16 for every
  screen and sheet; 24 between sections; 12 inside a section; 8 between a label and its field; no
  component sets its own outer margin.
- **Heights:** `control` 44 (buttons, inputs, selects, segmented control), `controlSm` 36 (compact
  buttons, chips, icon buttons in headers), `row` 56 (row with a detail line), `rowCompact` 48
  (one-line rows, options), `header` 52, `tab` 44, `dayPill` 44.
- **Touch:** every control reaches 48 dp with hit slop (recommended, decision D5; the brief's
  minimum is 44). One helper `touchSlop(height)` replaces the hand-written hit slops.
- **Fixed heights become minimum heights** so text can scale.

### 9.4 Radii, borders, shadows, icons

- **Radii:** `xs` 6 (check boxes, small tiles), `sm` 8 (thumbnails, notices, map tags), `md` 12
  (buttons, inputs, selects, drop-down lists, segmented control, day pills, tiles), `lg` 16 (cards,
  the legend), `xl` 24 (sheets and the sheets that curve over a cover or a map), `pill` (chips,
  badges, discs).
- **Borders:** `hairline` (dividers), `1` (control outlines in `outline`), `2` (focus ring, tab
  underline, selected outline). Nothing at 1.5, 2.5 or 3.
- **Shadows:** `none` by default; `card` for cards and floating map controls; `raised` for sheets.
- **Icons:** sizes 14 (inside metadata), 16 (in rows and compact controls), 20 (regular controls,
  list leading icons), 24 (bottom bar, header buttons); one stroke, 1.8. A `minus` icon is added
  for steppers. No characters as icons.

### 9.5 Components

| Component | Variants (all documented) | Replaces |
|---|---|---|
| `Button` | `primary` (filled), `secondary` (outlined), `ghost` (text), `destructive` (filled `danger`); `tone="danger"` for a ghost or secondary entry point ("Delete trip"); sizes `md` 44 and `sm` 36; radius 12; states default, pressed, disabled, loading, focused | `primary`, `ink`, `accent`, `quiet` |
| `IconButton` | `plain`, `onImage`, `onMap`; sizes `md` (44) and `sm` (36) | header buttons, map key, attribution "i", map panel close |
| `TextField`, `SearchField`, `SelectField`, `DateField` | one shell: caption label, 44 box, radius 12, 1 dp `outline`, 15 pt text, leading icon, suffix, clear button, hint, error, `multiline` | `Field`, `BoxField`, `Dropdown` field, Add-document box, hairline fields, city-search input |
| `Stepper` | `md`, `sm` | three steppers |
| `Chip` | `filter` / `choice` (one look), optional icon, 36 dp, selected = soft fill + `selected` border + check icon | `Chip`, Change-photo tabs, "✓ Selected" |
| `SegmentedControl` | 2–3 options, 44 dp, radius 12 | chips and tabs used as form switches |
| `Tabs` | `regular` (44), `compact` (40) | (kept) |
| `DayPills` | — | (kept, restyled to the selection rule) |
| `Badge` | `neutral`, `primary`, `accent`, `onImage`, `danger` | (kept) |
| `Card` | one look (radius 16, hairline, `card` shadow, padding 12) | `card` users; the old flat `Card` becomes `Section` |
| `CoverCard` | the trip card | (kept) |
| `ListRow` | leading (icon, tile, thumbnail, number, radio, check), title, up to two detail lines, trailing (chevron, badge, action, menu), `regular` 56 / `compact` 48, `selected`, `disabled` with reason, `danger` | `ChoiceRow`, `ResultRow`, city result, credit row, compare row, Optimize rows |
| `InfoRow`, `MetaLine` | label over value; icon and text | three `Fact`s |
| `ScreenHeader` | Back row + 24 pt title (+ subtitle, right actions) | `ScreenHeader`, `FormHeader`, new-trip header |
| `CompactHeader` | Back, 18 pt one-line title, subtitle, right actions | `CompactHeader`, overview inline header |
| `CoverHeader` | trip and place covers: scrim, Back and menu on the photo, hero text | two hand-made heroes |
| `SectionHeader` | title + optional action | `SectionTitle` and ad-hoc headings |
| `Sheet` | one look: `surface`, radius 24, grabber, `headline` title, close | (kept, restyled) |
| `ConfirmSheet` | title, message, destructive or primary confirm, cancel | three inline confirmations |
| `StateView` | `loading`, `empty`, `error`, `waking`, `offline`, `planned`; icon in a 48 dp soft circle, `headline` title, `label` text, optional `secondary` action; `fill` (centred) or `inline` | `LoadingState`, `EmptyState`, `ErrorState`, `WakingServer`, Trips empty tab, `PlannedFeature`, the Documents empty layout keeps its tiles inside it |
| `InlineStatus` | spinner `sm` + caption, or caption alone | "Searching…", "Reading the plan…" lines |
| `Notice` | `info`, `warning`, `error`, `success`; icon + word + text, radius 8, **no outer margin**, optional `ghost` action | `Notice`, `BackendBanner` |
| `Tile` | icon on a soft tone, 32 / 40 / 48, radius 8 / 12 | `KindTile`, option tile, past-trip tile |
| `StopMark` | sight (round), eat (rounded square), transport, city, day colour; 24 list / 26 map / 34 selected | list discs, map dots, legend keys, city numbers, day badges |
| `MapChip`, `MapButton`, `MapPanel` | — | map tags, key button, legend, failure, past-map panel |

---

## 10. Proposed changes for every screen

| # | Screen | Changes |
|---|---|---|
| S1 | Trips | Trip card name `headline` at weight 700 (18, from 22: a card title stays below the screen title) with the shared `textOnImage` shadow, dates `caption`; empty tab → `StateView inline`; New trip → `Button primary md`; badge on photo → `Badge onImage`; tabs unchanged |
| S2–S3 | Explore, Photos | `StateView planned` inside the gutter; header unchanged |
| S4 | More | Remove the double inset (rows full width, text at 16); disabled rows keep "Coming later"; note → caption |
| G1 | Bottom bar | Labels → `micro`; active colour → `selected`; Add disc → `primary` 40 dp; no layout change |
| G2 | Add to this trip | `Sheet` restyle only |
| G3 | Server banner | → `Notice` (`warning` / `error`) with a `ghost` Retry |
| S5 | Create new trip | `ScreenHeader`; destination → `SearchField`; chosen destination → `SelectField`-style chosen value with clear; start date → `DateField`; duration → `Stepper`; latitude / longitude → `TextField`s; public transport → `ListRow` with a switch; main buttons → `primary md` and `secondary md`; "Search more widely" `secondary sm`, "Enter it by hand" `ghost sm` (same everywhere); results drop-down unchanged |
| M1 | Calendar | Selected day → `selected`; day cells `minHeight` |
| M2 | Add a city | `SearchField`; results → `ListRow compact` with disabled reason; `InlineStatus` |
| M3 | Change photo | City tabs → `Chip`s; loading → `StateView inline`; grid unchanged |
| C1 | Stop list | `Stepper sm`; number → `StopMark city`; up / down / remove `IconButton sm` |
| S6 | Trip overview | `CoverHeader` (hero 26); sheet radius `xl` 24; body gutter fixed (timeline and Optimize row at 16); "Choose a plan" → `Card` with `primary md`; loading states keep the cover space with `StateView` instead of a `ScreenHeader` "Trip" |
| S7 | Map tab | `CompactHeader` (shared); map overlays → `MapChip`, `MapButton`, `MapPanel`; day pills to the selection rule; stop discs → `StopMark`; list gutter 16 (rows pad 8 inside the tint) |
| S8 | Photos tab | `StateView planned` |
| S9 | Documents tab | filter `Chip`s unchanged; "All documents" → `SectionHeader` with Sort `ghost sm`; rows → `ListRow` with `Tile` and a menu `IconButton`; empty → `StateView empty` around the four tiles; Add a document `primary md` |
| M4, M5 | Trip menu, sorting, document menu | `Sheet` restyle only |
| S10 | Proposals | `CompactHeader`; plan cards → `Card` (radius 16), title `cardTitle`, facts → `MetaLine`s, buttons `secondary sm` + `primary sm`; Compare row → `ListRow`; table `label` text; "Not planned yet" → `StateView empty` with `primary md` |
| S11 | Plan screen | Map / List `Tabs compact` unchanged; Add a place / Add a restaurant `secondary sm`; choose bar `primary md`; "✓ Selected" → `Badge primary` with a check icon |
| S12 | Place detail | `CoverHeader`; title `hero` 26 (token); display-name editor → `TextField`; Save `primary sm`, Cancel `secondary sm` (same as length editor); Remove → `secondary sm tone=danger`; facts → `InfoRow`; documents section `SectionHeader` |
| S13 | Optimize | Radio rows → `ListRow` with `Radio`; button `primary md` |
| M6 | Keep in place | Check rows → `ListRow compact` with `Checkbox`; Done `primary md` |
| S14 | Add a place | Search / Address / Pin → `SegmentedControl`; fields → `TextField` / `SearchField` / `SelectField` (44); "Suggest a day / Choose day and time" → `SegmentedControl`; suggestion cards → `Card`-free selectable rows with `Radio` (same mark as Optimize); main buttons `primary md`; `InlineStatus`; pin colour → `StopMark` selected |
| S15 | Add a restaurant | `CompactHeader` (as Add a place); Search / Enter by hand → `SegmentedControl`; fields → `SearchField`, `TextField`; results → `ListRow` with a `Radio`-free selected state and `KindIcon`; Kind → `Chip`s; buttons as in S14; map height and pin as in S14 |
| C2 | Choose slot | Fields at 44; button `primary md` |
| S16 | Change preview | `CompactHeader` with subtitle "Nothing changes until you accept."; summary → `Card`; diff sections → `SectionHeader` + bullet rows (`label`); Accept `primary md`, Discard `secondary md`; closed status `Notice` |
| S17 | Trip settings | `ScreenHeader` (large); each block → `Section` (headline + `label` text, 14 pt); actions `secondary sm`; Mark as past and Delete → `secondary sm tone=danger` opening `ConfirmSheet` with a `destructive` confirm |
| S18 | Edit cities | `Stepper`; button `primary md`; gutter fix for notices |
| S19 | Past trip | Day badges → `StopMark day` with contrast-safe colours; row tiles → `Tile` with `dayTones`; Skip / Restore → `ghost sm`; Documents and Export rows unchanged; map panel → `MapPanel` |
| S20 | Trip documents | Gutter fix only |
| S21 | Document | `ScreenHeader`; facts → `InfoRow`; Open `primary md`, Edit `secondary md`, Delete `ghost sm tone=danger` → `ConfirmSheet` |
| S22–S23 | Add document | `ScreenHeader` (FormHeader removed); option cards → `Card` + `ListRow` content; privacy box → `Notice info`; Title, Date, Notes → `TextField`, `DateField`, `TextField multiline` (outline 3:1); type and "Related to" `Chip`s; Save `primary md` |
| S24 | Export | `Section`s, `label` text, documents switch as a `ListRow` with a switch; Export `primary md` |
| S25 | Import | Trip list → `ListRow`s; buttons `primary md` / `secondary md`; reading → `InlineStatus` |
| S26 | Settings | Connection as `InfoRow`s; Check again `secondary sm`; credits as `ListRow`s with an external-link icon (same as Image credits) |
| S27 | Image credits | Rows → `ListRow` |
| P1–P3 | Maps, attribution | `MapChip`, `MapButton`, `MapPanel`; attribution "i" → `IconButton onMap` with the `info` icon; markers keep their sizes, shared with `StopMark` |
| P5 | Suggestion card | Becomes a selectable `ListRow`-like block with the shared `Radio`; title `cardTitle` |
| P6 | Plan summary card | Delete (unused) |

Information architecture: unchanged everywhere. Two interaction changes are proposed and need the
owner's OK (decision D4): confirmations move into a sheet, and Add a restaurant takes Add a place's
compact header.

---

## 11. Decisions needed from the owner before implementation

These touch earlier owner decisions (ADR 021) or the brief; the redesign follows the answers and
records them as an ADR 021 amendment (decisions 78 onward).

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | **The colour of the main action and of "selected".** ADR 021 made the main button navy (`ink`) and the day pills, tabs and calendar navy; the brief says "deep green primary". | (a) green (`primary`) for main buttons and every selected state; navy stays for text, transport markers and the selected map marker. (b) keep navy for main buttons and selection; green only for sights and brand. | **(a)**: matches the brief and replaces three selection colours with one. |
| D2 | **Button shape.** ADR 021 decision 49 made buttons slim pills; the brief asks for 10–12 radius buttons and fully rounded pills. | (a) buttons and fields radius 12, pills only for chips, badges and filters. (b) keep pill buttons. | **(a)**: an action and a choice look different. |
| D3 | **Page colour.** The brief says "warm off-white"; ADR 021 decision 25 replaced the warm `#f7f4ee` with near-white `#fcfcfb` as "too yellow". | (a) keep `#fcfcfb`. (b) a barely warm `#fbfaf7`. | **(a)**, unless the owner wants it warmer. |
| D4 | **Confirmations.** Inline blocks today. | (a) `ConfirmSheet` (a sheet with the message, a red confirm and Cancel). (b) one shared inline `ConfirmPanel` in the same place as today. | **(a)**: one pattern, and the red button stands apart. |
| D5 | **Minimum touch target.** The brief says 44; the app and its tests use 48 (Android guidance). | (a) 48 with hit slop, drawn controls 36–44. (b) 44. | **(a)** |
| D6 | **Screenshots.** Not possible in this container (section 12). | (a) add a Maestro "screenshot tour" to the E2E Android workflow and run it by hand before and after. (b) the owner's own screenshots from the phone. | **(a)**, plus the owner's look on a phone at the end. |

---

## 12. Validation plan

- **After every phase:** `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`
  (all jest suites, including `accessibility.test.tsx` and `theme.test.ts`).
- **New tests:** contrast of every new token and every day colour (`theme.test.ts`); a style lint
  test that fails when a file in `screens/` uses a hex colour, a literal `fontSize`, a literal
  `borderRadius` or a literal `fontWeight` outside the tokens (with an allow-list for section 13);
  component tests for `Button` (variants, states), `TextField` (error, hint, clear), `SegmentedControl`,
  `Stepper`, `ConfirmSheet`, `StateView`.
- **Text scaling:** fixed heights become minimum heights (checked by the style lint test); titles that
  truncate get two lines where the layout allows. A real check at 200 % font size needs a device.
- **Narrow screens and long text:** jest cannot lay out; this needs the screenshot tour on a 360 dp
  emulator with the font scale raised, and a run with long names in the fixtures.
- **Android device check:** "Android APK" workflow, then the owner on a phone, after phases 3, 5 and 6.
- **Screenshots (D6):** a Maestro flow `e2e/screenshot-tour.yaml` that visits every screen in the
  inventory with the e2e seed data and calls `takeScreenshot`; the "E2E Android" workflow uploads
  them as an artifact. Run once now for "before" and again at the end for "after". Screens that the
  seed cannot reach (offline, waking, errors) are listed as validated by tests only.

## 13. Proposed exceptions (to be confirmed at the end)

| Exception | Reason |
|---|---|
| Cover illustration palette (25 colours in `Cover.tsx`) | An illustration, not UI colour; contrast of the hills against white is tested |
| Map marker drawing (sizes 26 / 34, white edge 2) | Must read on any map tile; sizes shared through `StopMark` tokens |
| Day colours of past trips | A categorical palette; moved to `theme.ts` and tested |
| Map attribution text at 12 | OSMF attribution guideline layout; uses the `micro` token |
| Calendar grid cells | A 7-column grid; cells use tokens but their width is a seventh of the row |
| Wordmark size on Trips (31 dp) | An image, set by ADR 021 decision 68(c) |

## 14. Implementation phases (after the OK)

1. Audit and inventory — **this document**.
2. Tokens (`theme.ts`) and shared components (`components/ds/`), with their tests; old components
   kept as thin wrappers until their screens move, then removed.
3. Navigation, headers, sheets, states, notices, global layout (gutter, no outer margins).
4. Forms and creation flows: Create trip, Add a city, Add a place, Add a restaurant, Choose slot,
   Add document, Edit cities, display name and length editors.
5. Trips, overview, proposals, plan, maps, place detail, Optimize, Change preview, past trip.
6. Documents, Trip settings, Export, Import, Settings, Image credits, More, Explore, Photos.
7. Final review: the style lint test at zero, every screen of section 2 ticked, screenshots, this
   document's exceptions confirmed, `docs/design.md` rewritten (principles, tokens, type scale,
   spacing, component specifications, interaction states, approved exceptions), ADR 021 amended.

No backend, API, planner, routing or data change is part of any phase.

---

## 15. Progress (2026-11-15)

The owner accepted the recommendations for D1 to D6 (green main actions and selection; buttons and
fields at radius 12, pills only for chips, badges and filters; page `#fcfcfb`; confirmations in a
sheet; 48 dp touch targets with 36–44 dp drawn controls; a Maestro screenshot tour). They are
recorded as ADR 021, decisions 78 to 90, and the result is described in `docs/design.md`.

### Session 1 (phases 2 and 3, committed as work in progress)

Tokens and the shared components (`components/ds/`), navigation, headers and layout; much of phases 4
and 5 ahead of plan. The app did not build at the end of it.

### Session 2 (phases 2, 6 and 7 finished)

- **The build is repaired.** The seven screens that still imported the deleted modules (Trip
  settings, Document, Trip documents, Export, Import, Settings, Image credits) use `components/ds`:
  flat `Section`s, `InfoRow`s, `ListRow`s, `InlineStatus`, a switch row in Export.
- **Phase 6, confirmations.** Mark as past, Delete trip and Delete document ask in a `ConfirmSheet`
  with a `destructive` confirm; their entry points are `tone="danger"` buttons. No inline
  confirmation block is left. The sheet closes when the action fails, so the problem is in view.
- **Regressions found by the first full test run, and fixed in the components:** a disabled `ListRow`
  had lost its button role (it is announced as a dimmed button with its reason again); "Compare
  itineraries" had lost its expanded state (`ListRow` gained `expanded`); the server banner and the
  waking view said the same sentence twice (the banner is shorter). Test edits that follow the
  design: "Status: connected" is an `InfoRow` (matched by its spoken label), the notes counter is the
  field's hint ("11/500 characters"), a place's "Type: Restaurant" fact has no full stop, Add a
  restaurant's header is announced with its trip subtitle, "Saved for later" starts with a capital.
- **Phase 7.** `styleTokens.test.ts` (the style lint, zero violations; the only exception is the
  cover illustration palette), `e2e/screenshot-tour.yaml` and a `flow` input on the "E2E Android"
  workflow, `docs/design.md` rewritten (principles, tokens, components, states, rules the tests
  enforce, approved exceptions, how to check), ADR 021 amended (decisions 78 to 90), CLAUDE.md and
  `docs/development.md` updated.
- **Checks run:** `npm run format:check`, `npm run lint`, `npm run typecheck` and `npm test` (43
  suites, 458 tests) passed; session 3 below raised this to 468 tests.

### Session 3 (a second pass: the work checked against sections 3 to 10 and 13)

The owner asked for a double check of phases 2 to 7. Each item of the audit's lists was checked in
the code (not in the earlier summary). Found and fixed:

- **Focus (A8):** only `Button`, `TextField` and `IconButton` had a focus state, yet `design.md`
  claimed every control had. Now a shared `useFocusRing` and `FocusPressable` give `Chip`,
  `ListRow`, tabs, segments, the bottom bar, the select field, the calendar, cards, document rows,
  stop rows and the rest the same ring; tested per kind, and a test fails on a `Pressable` without it.
- **Hand-written hit slop** in the photo credit and the map attribution: now `touchSlop`.
- **Literal values the lint did not see:** seven `gap: 1`, a bullet margin, a suggestion indent, nine
  control heights (44, 48, 40, 52, 64, 72, 56, 52, 48) and the radio and check size, the Add disc
  (was 36, now 40 as planned): all tokens now (`size.radio`, `header`, `multiline`, `thumbPortrait`,
  `stateMark`, `creditButton`, `attributionButton`, `link`). The lint now also rejects numeric
  spacing, control heights and hand-written hit slop.
- **Map overlays (P1 to P3):** the failure message was copied into both maps and the key panel was
  styled by hand. Now `MapFailure` and `MapPanel` in `ds/map.tsx`. A tested `MapFailure`.
- **One-line truncation (A5):** titles on the trip card and cover, compact headers, cities and
  documents take two lines.
- **Test coverage of phase 6:** `accessibility.test.tsx` did not visit Trip settings (or its
  confirmation sheets), Export, Import, Image credits, More, Explore, Photos, Optimize, Add a
  restaurant or Add document. It does now, and I checked the new tests fail when the touch target
  shrinks.
- **Documents corrected:** the focus claim above, and the list of what the screens and tests cover.
- **Not built, on purpose** (recorded in `design.md`, "Where the build differs"): `CoverHeader`,
  `DateField`, `DayPills`, `CoverCard`, `MapButton`.
- **Checks now:** format, lint, typecheck and `npm test` pass: 43 suites, 468 tests.

### Still open

1. **The screenshot tour has never been run** (no emulator in the development container). It was
   written from the app's test IDs and may need an id or a wait adjusted on its first run.
2. **`e2e/trip-flow.yaml` is out of date with the screens** (it waits for "Your itinerary" and taps
   `open-itinerary`, neither of which exists since ADR 021; the comparison also opens from the
   "Compare itineraries" row now). It was already stale before this redesign and is not fixed here
   because it cannot be run to check a fix.
3. **Nothing has been checked on a device or in screenshots.** The owner's look on a phone is the
   real acceptance; text at 200 % font size and a 360 dp screen with long names need a device.
4. **Section 13's exceptions** are confirmed in `docs/design.md` ("Approved exceptions") but the
   owner has not yet signed them off.
