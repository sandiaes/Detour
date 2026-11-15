# Detour design

How the mobile app looks and behaves. It is the working reference for screens: build to it, and
change it in the same change as the screens (CLAUDE.md, "Update the affected documents").

- **Sources:** the reference screens in [`screenshots/`](screenshots/) (01 to 16), the app as built
  (ADR 015, 020, 021) and the owner's feedback of 2026-11-14. Where the reference screens show
  something Detour does not do (prices, ratings, photos, reviews), the screens win only on layout:
  the content rules of CLAUDE.md still apply (never invent data, no budgets, no LLM text).
- **Code:** tokens in `apps/mobile/src/theme.ts`, components in `apps/mobile/src/components/ds/`
  (imported from `components/ds`). No screen or component defines a colour, a font size, a weight, a
  radius or a border width of its own; `styleTokens.test.ts` fails when one does.
- **History:** the design-consistency audit of 2026-11-15 is `design-audit.md`; its answers are
  recorded as ADR 021, decisions 78 to 90. This document describes the app as built after it.
- **Not verified on a device:** the owner has seen the app on a phone, but the 2026-11-15 design
  system has been checked by tests and typechecking only, not by screenshot. The screenshot tour
  (see "Checking the design") has not been run yet.

## 1. Principles

1. **Clean, modern, minimal.** Few things on a screen, each with room. If a line of text repeats
   what the screen already says, it goes (a day's date, its counts and its base city are said once).
2. **Hairlines, not boxes.** Content sits on the page and is separated by 1 px lines. A card (a
   rounded white box with a hairline and a soft shadow, `card` in `theme.ts`) is kept only for a thing
   that is picked up and opened: a trip's cover, a proposal, a plan on the overview, a way to add a
   document and the file being added, and a sheet that slides over the page. Details screens, lists
   and figures have no cards.
3. **Near-white page, dark navy text, one calm green.** Deep green is the main action and every
   selected state; sights are green, places to eat are orange, transport markers are navy. Colour
   carries state and kind, never decoration, and never alone: a word or a shape says it too.
4. **Photos where the source has one, illustrations everywhere else, nothing invented.** A trip's
   cover on the Trips card and the trip header, and the photo of a place on its detail screen, are
   Wikimedia Commons photos the backend sends (ADR 022, step 3); a trip or place with none keeps the
   generated illustration. A photo has no dark band; **text sits on a photo only in the trip's
   header and on a trip card of the Trips list** (name, dates, length, in white over a soft top and bottom gradient; ADR 021, decision 43);
   everywhere else names and dates sit beside it. Its average colour shows while it loads. It is never shown without its author and
   licence, kept behind a small "i" in its bottom right corner (pressed, it shows "Photo: author,
   licence, Wikimedia Commons (resized)" and opens the file's page; `Cover` draws it, so no screen can
   forget it). A photo is never a map marker. **A photo fills its frame and the overflow is cropped**
   (ADR 022 amendment, decision e): a landscape photo is centred, a portrait photo is anchored about a
   third of the way down (`photoPlacement` in `Cover.tsx`); nothing is cropped in storage.
   **Optimize (ADR 029).** The trip menu and the top of the Overview offer **Optimize** when the
   plan has at least three stops with a place. A compact screen asks how far the order may change
   (two slim radio rows: within each day, or across all days) and has one "Keep in place" row (how
   many stops are kept) that opens a sheet with the stops by day: a stop a document is about starts
   selected, a locked stop is shown as kept; the screen itself never lists every stop. "Show a
   shorter order" opens the ordinary change preview titled "A shorter order?", with the saving in
   minutes and kilometres, whether times are estimated, "a shorter order, not necessarily the
   shortest" and "opening hours are not known" shown open, then Accept or Discard. When nothing is shorter the screen says so and changes nothing. Right after an
   Optimize the trip menu offers **Undo Optimize** (until the plan changes).
   **"Change photo"** (the new-trip screen under the destination, and the trip menu) opens a sheet of up
   to 12 photos of the destination, three across, each with its author and licence, and "Automatic
   photo" (`CoverPicker`). For a multi-city trip it has one tab per stop. A day of the Overview
   shows the photo of its first visit that has one. **More, Image credits** lists the author, licence
   and page of every photo the app holds.
5. **Honest about what is not built.** A control that does nothing yet says so in words
   ("Not built yet", "saved for later"). Nothing is faked.
6. **Small type, large targets.** Body text is compact; every control is still at least 48 dp tall
   (the accessibility test enforces it, using height plus hit slop).
7. **One of each.** One button, one field shell, one chip, one sheet, one confirmation, one set of
   loading, empty and error views. A screen picks a component and a variant; it does not restyle it.
   What differs between screens is content, never the look of a control.

### Brand

The logo is in `docs/brand/` (`detour-logo.png`: mark and wordmark; `detour-mark.png`: the rounded
mark alone). The launcher icon is the mark cut to a full-bleed square, `apps/mobile/assets/icon.png`,
shrunk to 69 % of the canvas as the Android adaptive-icon foreground (`adaptive-icon-foreground.png`),
over `adaptive-icon-background.png`, so a launcher's mask never cuts it (`apps/mobile/app.json`;
`expo prebuild` in the "Android APK" workflow picks it up). The Trips screen header is the
wordmark alone, "Detour" and its orange dot, on a transparent ground (`assets/detour-wordmark.png`).

## 2. Tokens

All in `apps/mobile/src/theme.ts`. Contrast of every text and background pair, of the day colours and
of the borders that identify a control is asserted in `theme.test.ts`.

**Colour**

| Token | Value | Use |
|---|---|---|
| `background` | `#fcfcfb` | The page (owner, 2026-11-15: keep the near white of ADR 021, decision 25) |
| `surface` | `#ffffff` | Sheets, cards, fields, map controls |
| `surfaceMuted` | `#f2f2f0` | A pressed row, a default value, quiet badges, info notices |
| `border` | `#e4e4e1` | Hairlines only; never the sole mark of a control |
| `outline` | `#7a858c` | Borders that identify a control (inputs, chips, outlined buttons, map lines): at least 3:1 |
| `text` / `muted` | `#14243a` / `#56616c` | Text; both at least 4.5:1 on the page |
| `primary` / `primaryPressed` | `#2b6b64` / `#225650` | The main action, links to the next step, sights |
| `selected` / `selectedSoft` | `primary` / `#e2eeeb` | **Every** selected state: tabs, chips, segments, day pills, radios, check boxes, calendar, bottom bar |
| `eat` / `eatSoft` / `accentText` | `#b5511c` / `#f9e8dc` / `#8a3b12` | Places to eat on the map and in lists; `accentText` for text on the soft ground |
| `ink` | `#14243a` | Transport markers and the selected map marker (not a button colour any more) |
| `danger` / `dangerSoft` | `#b42318` / `#fbe6e3` | The confirming button of a destructive action, a danger row; white on `danger` is 6.5:1 |
| `warning*`, `error*`, `link` | see `theme.ts` | Notices and links |
| `imageButton`, `imageOverlay`, `scrim`, `textShadow`, `onImage` | overlays | Controls, credits and text on a photo |
| `mapOverlay`, `backdrop` | `rgba` | Tags and buttons on a map; behind a sheet |
| `dayTones` | eight `{ fg, bg }` pairs | Past-trip days; white on each `fg` is at least 4.5:1 (three were darkened for it) |
| `docTones` | four pairs | The tile of a document's kind |

**Type** (`type` in `theme.ts`; weights from `weight`)

| Token | Size / line | Weight | Role |
|---|---|---|---|
| `hero` | 26 / 32 | 700 | The name on a trip or place cover |
| `title` | 24 / 30 | 700 | A screen's title (`ScreenHeader`) |
| `headline` | 18 / 24 | 600 | Section title, compact header and sheet titles, state titles |
| `cardTitle` | 16 / 22 | 600 | A card's or main row's title |
| `body` | 15 / 21 | 400 | Paragraphs, input text, regular button labels (600) |
| `label` | 14 / 20 | 400 to 600 | List titles (stops, choices, documents), compact button labels, field values |
| `caption` | 13 / 18 | 400 to 500 | Metadata, field labels, hints, chips |
| `micro` | 12 / 16 | 500 to 600 | Bottom-bar labels, badges, the map attribution |

**Space, shape and size**

- **Spacing** (`spacing`): 2, 4, 8, 12, 16, 24, 32. **Rules:** the screen gutter is 16 (`layout.gutter`)
  for every screen and sheet; 24 between sections (`layout.section`); 12 inside a section; 8 between a
  label and its field. **A component sets no outer margin**: the screen's gutter does (`Notice` has
  none; `inset` is the opt-in where its parent has no gutter).
- **Radii** (`radius`): `xs` 6 (check boxes, small tiles), `sm` 8 (thumbnails, notices, map tags),
  `md` 12 (buttons, inputs, selects, drop-down lists, segmented control, day pills, tiles),
  `lg` 16 (cards, the map legend), `xl` 24 (sheets and the sheets that curve over a cover or a map),
  `pill` (chips, badges, discs, switches).
- **Borders** (`border`): `hairline` (dividers), `thin` 1 (control outlines in `outline`), `thick` 2
  (focus ring, tab underline, selected outline). Nothing at 1.5, 2.5 or 3.
- **Shadows** (`shadow`): none by default; `card` for cards and floating map controls; `raised` for sheets.
- **Heights** (`size`): `control` 44 (buttons, inputs, selects, segmented control), `controlSm` 36
  (small buttons, chips, header icon buttons), `row` 56 (a row with a detail line), `rowCompact` 48,
  `tab` 44, `tabCompact` 40. A drawn height is a **minimum**, so text can scale.
- **Touch:** every control reaches 48 dp (`TOUCH`) with hit slop; `touchSlop(height)` is the one helper.
- **Icons** (`icon`): 14 in metadata, 16 in rows and small controls, 20 in regular controls, 24 in the
  bottom bar and on covers; one stroke width, 1.8. Icons are drawn shapes, never characters.

## 3. Components

Everything below is exported from `components/ds`. A screen uses these and nothing of its own.

| Component | Variants and rules |
|---|---|
| **`Button`** | `primary` (filled green): the screen's main action, **at most one per screen or sheet**. `secondary` (outlined): a second action. `ghost` (text): a third, quiet action. `destructive` (filled red): only the button that confirms something that cannot be undone. `tone="danger"` makes a secondary or ghost button the red entry point ("Delete trip"). Sizes `md` (44) and `sm` (36); radius 12; optional icon; `fill` stretches it. States: default, pressed, disabled, loading (spinner, announced as busy) and focused (2 dp ring) |
| **`IconButton`** | `plain`, `onImage` (translucent disc over a photo), `onMap`; sizes `md` and `sm`; always has a spoken label |
| **Fields** | `TextField`, `SearchField`, `SelectField` (opens a `DropdownPanel` of `ChoiceRow`s), the calendar field, all in one `FieldShell`: a caption label, a 44 dp box, radius 12, a 1 dp `outline` border, 15 pt text, optional leading icon, suffix, clear button, hint (a counter such as "11/500 characters" is a hint) and error. `multiline` grows from three lines |
| **`Stepper`** | A number with minus and plus, sizes `md` and `sm` (days, a city's days, a length) |
| **`Chip`** | The one filter or choice look: a 36 dp pill with an `outline`; selected is a soft green fill, a green border and a check; announced as selected |
| **`SegmentedControl`** | Two or three exclusive options in one 44 dp control of radius 12 (Search / Address / Pin on map; Suggest a day / Choose day and time; Within each day / Across all days); a form switch, not navigation |
| **`Tabs`** | Underlined text tabs, `regular` (44) and `compact` (40); the selected tab is green with a 2 dp line |
| **`Radio`, `Checkbox`** | The marks of a one-of and a many-of list; used inside `ListRow` |
| **`ListRow`** | The one row: a leading icon, tile, thumbnail, number, radio or check; a title; up to two detail lines; a trailing chevron, badge, switch or action; `regular` 56 or `compact` 48; `selected`, `checked`, `expanded`, `danger`. **A disabled row stays announced as a button, dimmed, with its reason in words ("Coming later", "Choose a plan first")** |
| **`RowGroup`, `InfoRow`, `MetaLine`, `Bullets`** | Rows divided by hairlines; a fact (a small label over its value, over a hairline); an icon and a quiet line; short lines with bullets |
| **`Badge`** | A small pill with a word: `neutral`, `primary`, `accent`, `onImage`, `danger`; the word carries the meaning |
| **`Card`** | White, radius 16, a hairline, the `card` shadow, padding 12. Only for a thing picked up and opened (a proposal, a plan on the overview, a way to add a document, the file being added). **`Section`** is the flat block of a settings-like page: a hairline, a headline and its content, no box |
| **`Tile`, `StopMark`** | An icon on a soft tone (32, 40, 56). The mark of a stop, shared by the day list, the map and its key: round and green for a sight, a rounded square and orange for a place to eat, a navy rounded square for travel, a city or a day colour |
| **`Sheet`** | A white surface with 24 dp top corners, a grabber, a headline title and a Close button, over a `backdrop`; Android Back and a tap outside close it |
| **`ConfirmSheet`** | **The one confirmation** (decision 81): a sheet with the title as a question, one sentence on what will happen, a **`destructive` confirm** and a `secondary` way back. Used to delete a trip, mark it as past and delete a document. The entry point is a `secondary` or `ghost` button with `tone="danger"`. When the action fails the sheet closes so the problem notice is in view |
| **`StateView`** | The loading, empty, error, waking, offline and planned views (`LoadingState`, `EmptyState`, `ErrorState`, `WakingServer`, `PlannedFeature`): an icon in a 48 dp soft circle, a headline, a label-size text and an optional secondary action; `fill` centres it, `inline` sits in the page. **`InlineStatus`** is a spinner and a caption ("Searching…") |
| **`Notice`** | `info`, `warning`, `error`, `success`: an icon, a word (Note, Offline, Problem, Done) and the text, radius 8, no outer margin, an optional action |
| **Headers** | `ScreenHeader` (Back, a 24 pt title, a subtitle, right actions: Trips, More and pushed screens), `CompactHeader` (Back, a one-line 18 pt title, a subtitle, an action: screens inside a trip), `CoverBar` (Back and menu over a cover). A header is announced when its screen opens |
| **Other** | `StatRow` (flat figures), `SectionHeader` (a title and an action), `Cover`, `CoverPicker`, `Calendar`, `KindIcon`, `SuggestionCard`, `MapChip`, `EdgeFade` |

### Interaction states

Every control has, and the tests check, these states: **default**, **pressed** (a tint, never only
a colour change that is the sole cue), **disabled** (dimmed, announced as disabled, the reason in
words where a row is disabled), **loading** (a spinner in the button, announced as busy, pressing
does nothing), **focused** (a 2 dp green ring for keyboards and switch access), **selected** (green,
announced as selected) and **error** (a red border and a message under a field).

### Patterns

| Pattern | What it is |
|---|---|
| **Hairline row** | Icon or number, text, chevron, a hairline under it (`ListRow`). Lists, menus, stops, search results |
| **Flat figures** | Numbers with a small label in a row, separated by hairlines (`StatRow`) |
| **Sheet over a cover** | A white surface whose top corners curve over what is behind it: the trip's tabs over its cover, the stops over the map, the Add menu |
| **Soft edge** | A 10 dp fade at the top and a 14 dp fade above the bottom bar (`EdgeFade`); no hard line or shadow between the page and the bars |
| **Drop-down** | A boxed field that opens a short scrolling list under it (Add document, Attraction, Day) |
| **Planned feature** | Says what a part will do and "Not built yet" (`PlannedFeature`) |

## Rules the tests enforce

- `styleTokens.test.ts`: no file under `src` (apart from `theme.ts`, tests and the exceptions below)
  contains a hex or `rgba` colour, a `fontSize`, `lineHeight`, `fontFamily` or numeric `fontWeight`,
  a non-zero `borderRadius` or border width as a number, or `StyleSheet.hairlineWidth`. It also
  fails if a removed module (`ui.tsx`, the old `Button`, `BoxField`, `Dropdown`) comes back.
- `theme.test.ts`: contrast of every text pair, the border colours, the day colours and `danger`;
  `touchSlop`.
- `accessibility.test.tsx` and the screen tests: a spoken name for every control, 48 dp touch targets,
  states told in words, announced headers.
- `components/ds/components.test.tsx`: the variants and states of `Button`, the fields, `Stepper`,
  `SegmentedControl`, `ConfirmSheet`, `StateView`.

## Approved exceptions

Values that are not in `theme.ts` on purpose (decision 90). A new one needs the owner's approval.

| Exception | Where | Reason |
|---|---|---|
| The cover illustration palette (25 colours) | `components/ds/Cover.tsx` | An illustration, not UI colour. Allowed in `styleTokens.test.ts`; the contrast of its hills against white is tested |
| Marker sizes 26 and 34, white edge 2 | `StopMark`, the maps | Must read on any map tile; the sizes are tokens (`size.marker`, `size.markerSelected`) shared by the list, the map and the key |
| Map attribution text at 12 | `AttributionBar` | OSMF attribution layout; it uses the `micro` token |
| Calendar grid cells | `Calendar` | A seven-column grid: a cell is a seventh of the row; its text and colours are tokens |
| Wordmark width on Trips | `TripsScreen` | An image, set by ADR 021, decision 68 (c) |
| Geometry of drawn shapes (a radio's 20 dp circle, a 4 dp grabber, a 10 dp timeline dot, a 3 dp tab marker) | `ds/`, `nav/` | Shapes, not text or colour; plain width and height numbers are not linted |

## Checking the design

- **After every change:** `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`.
- **The screenshot tour** (`apps/mobile/e2e/screenshot-tour.yaml`, decision 83): Actions, "E2E Android",
  Run workflow, flow `screenshot-tour`. It drives the seeded fixture backend on an emulator, visits
  about thirty screens (Trips, Explore, Photos, More, Settings, Image credits, Import, Export, Create
  trip, the calendar, the proposals and their comparison, the overview, the map, a place, Edit
  length, Documents, Add document, the trip menu, Optimize, Trip settings and its confirmation, Add a
  place) and uploads the screenshots as an artifact. Run it before and after a design change. It
  cannot reach offline, waking, error states, a past trip or photos; component tests cover those.
  **It has not been run yet** (no emulator in the development container).
- **A phone:** the owner's look on a real device after the "Android APK" workflow. A check at 200 %
  font size and on a 360 dp screen with long names needs a device or the tour with the font scale raised.

## 4. Screens

### Trips (screen 01)

Title "Trips", tabs Upcoming and Past. Each trip is **one cover card** and nothing else: the
cover with the status badge on its own pill at the top right, and the trip's **name** and its
**dates and length** ("12–19 Mar 2026 · 8 days") **on the photo**, bottom left, in white over the
cover's soft gradient (owner, 2026-11-14, as screen 01). No footer, no counts, no destination line, no extra request per card. A button "New trip" ends the Upcoming list.

**A trip is named after its destination** (the country, region or city chosen), never with its
length: "Austria", not "Austria, 8 days". A multi-city trip is named by the server from its cities
(owner, 2026-11-14): "Vienna to Salzburg" for two, "Multi-city Austria" for three or more in one
country, else "Multi-city Central Europe" (a fixed table of regions), "Multi-city Europe" or
"Multi-city trip". The name follows edits of the cities.

### Create new trip (screen 13)

Back, then the title "Create new trip" and one line of subtitle. Then, as hairline fields:

1. **Destination:** a pin icon, the search field (any place), results as
   hairline rows. Every result can be chosen (ADR 027); one with no sight data (outside the
   available regions, from Photon, or typed by hand) says so and offers only **Start a fresh
   trip**, "Generate itineraries" being disabled with the reason. **Search more widely** asks Photon
   for any place; **Enter it by hand** takes a name and typed coordinates (a decimal comma is
   accepted). A place trip has no "Add another city", no proposals in its menu or settings, and
   "Change photo" only when the place is in the gazetteer (otherwise the illustration stays). Once chosen, the name with its kind and
   country, an X to clear it, and the destination's cover illustration beneath.
   **Add another city** (a quiet text button under a chosen city) makes it a **multi-city trip**
   (ADR 024): a sheet searches cities only, and the cities become hairline rows (a navy number
   disc, the name, minus and plus for its days, Up and Down to reorder, an X to remove) with
   "3 cities · 7 days in all" under them and "Add another city" again, up to six. The days are split
   evenly when the second city is added. With one city left it is an ordinary city trip again.
   Areas cannot be stops. "Change photo" offers one tab per city.
2. **Start date** (optional) and **Duration** (days, with minus and plus) side by side; for a
   multi-city trip the duration is the cities' total and cannot be set on its own. The start
   date opens a **month calendar** in a sheet (Monday first, today ringed, "Clear the date"); a date
   is chosen, never typed.
3. **Public transport:** a switch (there is no travel style: it did nothing).
4. A line: public transport is saved for later; the plans do not use it yet.
5. Two buttons, full width:
   - **Start a fresh trip** (`primary`, the main action): creates the trip and an empty plan, one empty day
     per trip day, chosen as its itinerary at once. No proposals. The trip opens on its overview.
   - **Generate itineraries** (`secondary`): creates the trip and the two proposals to compare. Sights
     only, with a midday gap, no restaurants.

   The fresh trip comes first (ADR 026, built). A trip whose dates are all in the past is created
   the same way (the calendar does not block past dates); the user fills it and marks it past, and
   it is not archived by itself (the two-day rule applies only to trips made before their last day).

Removed from the screen of the reference image: interests, budget and "Include popular
highlights" and the personalised-itineraries note. "Change photo" is a small outlined button under
the destination's cover; the photo chosen there becomes the trip's cover as soon as it is created. The trip name is
not asked; it is the destination.

### Trip overview (screens 02, 12)

- **The cover is the header.** The photo fills the top of the screen, under the status bar. Back and
  the trip menu sit on it at the top; the trip's **name, dates and length** sit on it bottom left in
  white ("Austria", "12 – 19 Mar 2026 · 8 days"), over a soft gradient. No destination or status
  line, and no header row above the photo.
- **A white sheet curves over the cover's lower edge** and holds the tabs: Overview, Map,
  Photos, Documents, which are spread across the full width with equal gutters at both edges and equal space between the labels; the map header uses the same tab height, so the line sits at the same place on every tab. The tabs stay at the top when the page scrolls. Only Map gives
  up the cover.
- **Overview tab = the itinerary (screens 02, 12):** three figures in the original stacked form, tighter (icon and number side by side, the word under them), **cities, places, restaurants** (icon, number, word; no number of days: the header says it);
  **Optimize** when the plan has three stops; then the trip's days as a **timeline**: a dot on a
  thin rail, a small thumbnail (no photo "i" on it; the credit is on the place's own screen), "Day 3 · Wed 14 Mar", the town, "4 activities · 2
  restaurants". A day opens the **Map tab on that day**. There is no "Your itineraries" block and no
  separate Itinerary tab: the original proposals are in the trip menu and new ones in Trip settings.
- **Map tab (screens 03, 14):** a compact header (small Back and menu buttons, the name) and the tabs close
  together, then the map (clipped to its area; the attribution "i" sits above the sheet's curve) of the day, then **the day pills**, then the day's stops. It uses the whole screen.
- **Photos:** a planned feature.
- **Documents (screens 15, 16, ADR 023):** see "Documents" below.

### The day: map and stops (screens 03, 12)

- **The stops get most of the height.** The map is the smaller part (about a third of the space
  between the tabs and the bottom bar), the stops the larger. The map's camera fits the day's stops.
- **Day pills sit under the map, above the stops** (screen 14): rounded pills (radius 12), 44 dp tall, that share the width
  (and scroll sideways when there are many days), the chosen one green with white text, in the stops' own type size. "Day 1" over
  "Thu, 12 Mar", or just "Day 1" when the trip has no dates; the text is **centred** in every pill.
- **Coming back keeps your place.** Back from a stop's details returns to the same day and the
  same selected stop (kept in the route), never to the first day.
- **No day title above the stops.** The pills say which day it is; there is no "Day 3, Wed 14 Mar,
  8 visits, 2 meals, 4 h at the sights, 1 h travelling" block. A trip
  that moves between base cities shows the day's base city as one quiet line.
- **A stop is a hairline row:** the time (start over end), a numbered disc that matches the map
  marker, the name in small bold, the **kind icon** and the kind and length in caption ("Attraction ·
  2 h", "Restaurant · 1 h 15 min"), a chevron to the place's details. The names are English where
  the source has an English name; the local name is on the place's details. Selecting a stop gives
  its row a soft rounded tint (the list is 8 dp from the screen edge and a row pads its content by
  12 dp, so the time, the disc and the chevron all have the same room) and highlights its marker, and the map moves to it; nothing opens under it. Lock and Remove are on the place's details.
- **A journey to the next city whose time is not known** (into or out of Japan, ADR 024) reads
  "Travel from Tokyo · time not calculated: public transport is not built yet"; its transport marker
  stays, with no line to it.
- **Travel between stops** is written into a hairline: a line, "Walk · 3 min · 170 m" in muted caption,
  a line. A stop row has no hairline of its own, so that travel line is the only divider between two stops. No Routed or Estimated tag (the spoken label still says when a time is an estimate).
- **Type sizes here are small** (name 14, details 13) so more stops show at once.

### Kind icons

One small icon says what a place is, wherever places are listed (day list, place detail, search
results, figures): a **fork and knife** for a restaurant, a **coffee cup** for a café, a **visitor at
a landmark** for an attraction (`KindIcon`). A word always sits beside it.

### Map markers

Small, flat and quiet (screen 03's discs, without the heavy rings):

| Marker | Look |
|---|---|
| Sight | 26 dp teal disc, white number, 2 px white edge, a light shadow |
| Place to eat | the same size, orange, rounded-square instead of round |
| Travel to a new base city | the same size, navy, rounded-square, a transport icon |
| Selected | 34 dp, navy, white edge |
| Lines | 2 px grey; solid when routed, dashed when estimated; straight, not the road path |

Each marker keeps a 48 dp touch area around the drawn shape. The map key (a 36 dp flat button;
Attraction, Restaurant or café, Travel to a new base city, the line) and the attribution stay.
A past trip's map uses the same markers: cities navy with a city icon, attractions teal.

### Place detail (screen 04)

Cover (only the Back button over it) that runs under the status bar to the top of the screen, like a
trip's cover, with no fade over it; then a white sheet whose top corners curve over its lower edge.
On it: the name the server resolved (ADR 025) and, under it in the muted small style, the original
local name when it differs; a name Detour romanized itself adds "Automatically romanized" in italics;
then "Edit display name" (a small outlined button opening a one-line field with Save and Cancel; an
edited name offers "Use the usual name"); one line with the kind icon,
the kind and the town ("Attraction · Vienna"); two flat figures for the day
("Day 3", "Wed 14 Mar") and the length ("1 h 30 min", "Typical visit" or "Set by you"); one quiet line with the
address (no label); for places to eat the kind and, when Photon gave one, the address (*ADR 026: the meal, venue and cuisine lines go*); small buttons Show
on map, **Edit length**, Lock, Remove (red outline) and Add a document. Edit length opens one field (minutes or
"1h30"), a "Default" pill that goes back to the usual length, Save and Cancel, and a live check: a
length that runs into the next timed stop is a conflict and cannot be saved; too little time for
the trip to the next stop, or an end after 20:00, is a warning that can be saved; the place's documents; the data source. No opening hours, no
"why it is in the plan", no rating, price or description (CLAUDE.md rule 5).

### Proposals (screen 14)

"Choose your itinerary", a sentence ("We've created two options for your 2-day trip to Salzburg…"),
the dates and length, then **the two plans as cards** (white, hairline, soft shadow): the cover, a badge ("Best-known sights",
"More variety"), the name ("Classic Salzburg", "Salzburg & beyond", from fixed templates),
"The essentials" / "A wider experience", the profile's sentence, then places, restaurants and
travel time from the plan's own numbers, and two small buttons: **View details** (`secondary`) and **Choose
this itinerary** (`primary`). A **Compare itineraries** row opens the comparison table; "You can always
adjust your itinerary later" ends the page. After new proposals were asked for, the plan chosen
earlier is kept apart with a note. **View details** opens that plan's map with the day pills under
it and the stops below, and "Choose this itinerary" under them. Not built from the mock: a
"Recommended" badge (nothing says one plan is better), city count and "Mostly walking" (a summary
has neither), "Add to Day 1" (a proposal is not edited).

### Add (screens 05, 06)

Add is contextual. On a trip: Place and Restaurant, with up to three suggested days or meal slots
from the recalculation, each a hairline row with its reasons; the preview shows the diff before
anything changes. Outside a trip it starts a new trip.

**Add a place** is built from drop-downs (ADR 021, decisions 69 and 70): a compact header, slim
tabs (Search, Address, Pin on map), and a boxed search field whose results open as one rounded list
under it, grouped under small headings ("Sights", "Towns and cities"). Choosing a result closes the
list and the field shows only the choice, with its kind and town; pressing it searches again. Then
**How long**: one boxed field (minutes, or "1h30") and a pill for the default ("Typical length" for
a sight; "Default · 2 h" for a town, 1 h for any other place); typing replaces the default. Then
either "Find the best day" (`primary`) with up to three suggested days, or, for "Choose day and
time" and for an empty trip, a **Day drop-down**, a start time field and "Add to day N at HH:MM".
Add a restaurant or café uses the same day drop-down and fields; its default pill is 1 h 15 min
for a restaurant and 45 min for a café (*proposed*).

### Documents (screens 15, 16)

- **The tab, empty:** a small illustration, "No documents yet", a sentence, **one row of four
  small tiles** (Tickets, Bookings, Transport, Other; icon over name) that start adding that kind,
  "Add a document" (`primary`) and the line that documents stay on this phone. There is no Insurance kind;
  a document saved as one reads as Other.
- **The tab, with documents:** filter chips (All and the four kinds), "All documents" with **Sort**
  (newest, oldest, title), then rows: a tinted tile for the kind (`docTones`), the title, "Ticket ·
  PDF · 245.0 kB", the document's date (or what it is about), a thumbnail for a picture, and a "…"
  menu (Open, Edit).
- **Add document, step one:** a compact top bar (Back, "Add document", the trip), then **cards**:
  "Upload from device" (the system file picker: PDFs and pictures, and Google Drive through
  Android's picker) and "Take a photo" ("Coming later"), and a "Your documents stay private" note.
  No link and no "Create a document" option.
- **Add document, step two:** the file as a card (picture or kind tile, name, size, a **Replace file**
  pill with a refresh icon); **Document type** chips with icons; **Title** (filled from the file
  name, with a clear button); **Related to**: Whole trip or Attraction (a drop-down of the plan's
  stops, closed until opened); a document saved earlier about a day or a journey keeps that link; **Date** (optional, the calendar);
  **Notes** (optional, 500 characters, with a counter), all as boxed one-line fields. "Save document" is
  disabled until a file, a title, a type and a complete link are chosen. Back from the form (or
  from a saved document) returns to the Documents tab.
- **A document:** its title, its kind as a tile and badge, a picture in place for images, then
  hairline facts (About, File, Type and size, Date and Notes when set, Added). Open (`primary`, the
  phone's viewer), Edit (`secondary`), Delete (red text, asks first in a confirmation sheet).
- **A place's details** list that place's documents under "Tickets and documents" (sights) or
  "Bookings and documents" (places to eat), with "Attach a document".
- **A past trip** is a flat page: a compact header with the settings icon, a summary, a Documents
  row, underlined Map, Days and List tabs, and hairline rows with plain Skip and Restore actions
  (the visited mark of every stop, restaurants and cafés included). **Days** (ADR 026, built) is the
  day record: a heading per day ("Day 2 · Sun 2 May") and its stops in their planned order, each
  as "Café · 11:30 · 45 min" (kind, start and length when they were kept; a trip archived before
  `0015` has no times and says so, pointing to the list). No routes or travel times.

### Edit cities (multi-city trips, ADR 024)

Trip settings shows "Your cities" with the list in words and **Edit cities**: the same rows as the
new-trip screen. With a chosen plan the main button is "Preview the change", which opens the change
preview ("Change your cities?", the diff, and a note naming what leaves with a removed day, marked
"added by you" or "locked"); without one it is "Save cities". Proposals made for the earlier cities
say "Made for the trip's earlier cities" and their "Choose this itinerary" is disabled.

### Trip settings, Export, Import, Settings, Image credits

Pushed screens with a `ScreenHeader` and the 16 dp gutter. **Trip settings** is flat `Section`s
(Your cities, Proposals, Mark as a past trip, Delete this trip): a headline, a label-size
explanation and one small button. **Mark as past trip** and **Delete trip** are `secondary` buttons
with `tone="danger"`; each opens a `ConfirmSheet` ("Mark as a past trip?", "Delete this trip?")
whose red button says what will happen ("Yes, mark as past", "Yes, delete the trip") and whose way
back is "Keep planning" or "Keep the trip". **Export** has one `ListRow` with a switch for the
documents and, when they are included, a warning `Notice` that the file is not encrypted; **Import**
lists the trips in the file as `ListRow`s; **Settings** shows the connection as `InfoRow`s and the
credits as link rows with an external-link icon; **Image credits** lists the photos the same way.
A document's own screen has facts as `InfoRow`s, Open (`primary`), Edit (`secondary`) and Delete
(red text), which asks in a `ConfirmSheet`.

### Photos, Explore, More (screens 07, 10, 11)

Planned features and a menu of hairline rows. Items that are not built say "Coming later".

## 5. Plans and times

- **Suggested plans have no meals (ADR 026, built).** Each day has one
  unplanned gap at midday (90 minutes, starting 12:30 to 14:00). It is not an item: the app draws it
  as a "Free time" hairline row ("Free time · 1 h 30 min · 12:45 to 14:15") with no kind icon and
  no place, derived from any idle stretch of 30 minutes or more between two stops after the
  transfer between them (`freeStretch` in `domain/itinerary.ts`); plans made by hand show it too.
  The proposals' comparison has no "Places to eat" row unless an older plan has some. The day runs 09:00 to 20:00. A restaurant or
  café is a stop the user adds; it reads "Restaurant · 1 h 15 min" or "Café · 45 min", with no
  Lunch or Dinner label, no cuisine and no meal type. Everything below about meal times describes
  the app until step 2 is built.
- **Meals are aimed at lunch 13:00 and dinner 20:00** (owner, 2026-11-14; *to change, ADR 026*). Windows: lunch 13:00 to
  15:00, afternoon snack 15:00 to 17:30 (Wider only), dinner 20:00 to 22:00. A meal starts at its
  window's start at the earliest. The day runs 09:00 to 22:00 so a 90-minute dinner at 20:00 ends
  inside it. The sightseeing allowance is unchanged: the evening that the longer day added is
  reserved as unplanned time (`Profile.free_minutes`), so days are not packed with more visits.
- The two plans can be compared, chosen, extended and recalculated as before (ADR 014 to 019).
- An empty trip has a plan of kind "Manual": days with nothing in them.

## 6. Accessibility

Unchanged by the restyle and tested: a spoken name for every control, 48 dp touch targets, states
told in words (selected, disabled, routed or estimated), text scaling, no colour-only meaning, and
the screen reader announcing a screen's title on arrival.

## 7. Open points

- **ADR 026 (proposed):** the midday gap numbers, the day window, the default lengths of a
  restaurant (75 min) and café (45 min), and how a "Free time" row looks are proposals for the
  owner to confirm on a device.
- **Adding places to an empty trip.** An empty trip is a manual plan. The Add-place and Add-a-
  restaurant flows (ADR 018, 019) recalculate planned itineraries and refuse a manual one
  ("not recalculable"). Adding a place to an empty day by hand needs its own flow: choose the day,
  say how long to stay (a manual item has no default length), and place it by hand. It needs the
  owner's approval and an amendment to ADR 021 before it is built.
- **Public transport** is stored nowhere (the travel-style choice was removed). Using it needs a field on the trip
  and a rule in the planner, with an ADR.
- **Photos are not checked on a device.** The crop rule and the "Change photo" sheet are tested by
  component tests only; a look on a small phone and a tablet is still owed (brief, Part 2a).
- **English names** (ADR 025) come from the user's own name, Wikidata, English Wikipedia, OpenStreetMap
  and safe romanization, in that order; the rest keep their local name. Wikidata names arrive in the
  background, so a place may show its local name on the first look. Not checked on a device.
- **Notes, reservations, trip summary:** ADR 021, "Not built". Documents are built (ADR 023) and
  are kept on the phone only; a trip file (ADR 028) carries them, unencrypted and only when the user
  chooses, from "Export trip" and "Back up all trips".
- **Dark mode** is not designed.
- **The screenshot tour has not been run** and the existing `trip-flow.yaml` is out of date with the
  screens (it looks for "Your itinerary" and `open-itinerary`, which no longer exist). Both need a
  first run on the emulator; see "Checking the design".

**Past trip (2026-11-15):** no storage or "routes are not kept" notes. Each day has a colour (eight, repeating)
used for its markers on the map, its badge in the Days tab and the icon tile of its rows; the map's legend is
a row of day chips; a tapped marker opens a panel with a coloured tile, the name, kind and day, and a close button.
