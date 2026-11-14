# Detour design

How the mobile app looks and behaves. It is the working reference for screens: build to it, and
change it in the same change as the screens (CLAUDE.md, "Update the affected documents").

- **Sources:** the reference screens in [`screenshots/`](screenshots/) (01 to 16), the app as built
  (ADR 015, 020, 021) and the owner's feedback of 2026-11-14. Where the reference screens show
  something Detour does not do (prices, ratings, photos, reviews), the screens win only on layout:
  the content rules of CLAUDE.md still apply (never invent data, no budgets, no LLM text).
- **Code:** tokens in `apps/mobile/src/theme.ts`, components in `apps/mobile/src/components/ds/`
  and `components/ui.tsx`. No screen defines a colour or a font size of its own.
- **Not verified on a device:** the owner has seen the app on a phone, but this document and the
  2026-11-14 restyle have been checked by tests and typechecking only, not by screenshot.

## 1. Principles

1. **Clean, modern, minimal.** Few things on a screen, each with room. If a line of text repeats
   what the screen already says, it goes (a day's date, its counts and its base city are said once).
2. **Hairlines, not boxes.** Content sits on the page and is separated by 1 px lines. A card (a
   rounded box with a border or shadow) is kept only for a thing that is picked up and opened: a
   trip's cover on the Trips screen, and a sheet that slides over the page. Details screens, lists,
   forms and figures have no cards.
3. **Near-white page, dark navy text, one calm accent.** Colour carries state and kind (a place to
   eat is orange), never decoration, and never alone: a word or a shape says it too.
4. **Photos where the source has one, illustrations everywhere else, nothing invented.** A trip's
   cover on the Trips card and the trip header, and the photo of a place on its detail screen, are
   Wikimedia Commons photos the backend sends (ADR 022, step 3); a trip or place with none keeps the
   generated illustration. A photo has no dark band or scrim and **no text over it**: names and dates sit
   beside it. Its average colour shows while it loads. It is never shown without its author and
   licence, kept behind a small "i" in its bottom right corner (pressed, it shows "Photo: author,
   licence, Wikimedia Commons (resized)" and opens the file's page; `Cover` draws it, so no screen can
   forget it). A photo is never a map marker. The "Change photo" control of screen 13 is not built yet (ADR 022,
   decision 15).
5. **Honest about what is not built.** A control that does nothing yet says so in words
   ("Not built yet", "saved for later"). Nothing is faked.
6. **Small type, large targets.** Body text is compact; every control is still at least 48 dp tall
   (the accessibility test enforces it, using height plus hit slop).

### Brand

The logo is in `docs/brand/` (`detour-logo.png`: mark and wordmark; `detour-mark.png`: the rounded
mark alone). The launcher icon is the mark cut to a full-bleed square, `apps/mobile/assets/icon.png`,
also used as the Android adaptive-icon foreground over the dark green `#1b3f36`
(`apps/mobile/app.json`; `expo prebuild` in the "Android APK" workflow picks it up). The Trips
screen header reads "Detour", the app name.

## 2. Tokens

| Token | Value | Use |
|---|---|---|
| `background` | `#fcfcfb` | The page. Near white; the earlier warm beige `#f7f4ee` was too yellow |
| `surface` | `#ffffff` | Sheets, map controls, badges on images |
| `surfaceMuted` | `#f2f2f0` | A selected row, quiet chips and badges |
| `border` | `#e4e4e1` | Hairlines only; never the sole mark of a control |
| `outline` | `#7a858c` | Borders that identify a control (inputs, chips, map lines): at least 3:1 |
| `text` / `muted` | `#14243a` / `#56616c` | Text; both at least 4.5:1 on the page |
| `primary` | `#2b6b64` | Sights, selected tab and chip, links to the next step |
| `eat` | `#b5511c` | Places to eat, on the map and in lists (`accentText` `#8a3b12` for text) |
| `ink` | `#14243a` | The one dark filled button of a screen, transport markers, the selected marker |

Type (`type` in `theme.ts`): display 30 (screen titles), title 22, heading 18, body 16, small 14,
caption 13. Lists of stops use small and caption; only the screen title is large. Spacing steps
2, 4, 8, 12, 16, 24, 32. Radii: 8, 14, 20, pill; sheets curve their top corners by 28.

Contrast of every text and background pair is asserted in `theme.test.ts`.

## 3. Patterns

| Pattern | What it is |
|---|---|
| **Hairline row** | Icon or number, text, chevron, a 1 px line under it. Lists, menus, stops, search results |
| **Flat figures** | Numbers with a small label in a row, separated by hairlines, a hairline above and below (`StatRow`) |
| **Underlined tabs** | Text tabs with a 2 px line under the selected one (`Tabs`); a day strip uses the same look |
| **Sheet** | A white surface whose top corners curve over what is behind it: the trip's tabs over its cover, the stops over the map, the Add menu |
| **Field** | A small label over the value, over a hairline, with a leading line icon. No box |
| **Chip** | A pill with an outline, filled soft green when selected, announced as selected |
| **Button** | `ink` filled for the screen's main action, outlined for the second, plain text for the third |
| **Badge** | A small pill with a word ("Upcoming"); the word carries the meaning |
| **Planned feature** | Says what a part will do and "Not built yet" (`PlannedFeature`) |

## 4. Screens

### Trips (screen 01)

Title "Trips", tabs Upcoming and Past. Each trip is **one cover card** and nothing else: the
cover, the status badge on its own pill at the top right of the photo, and under the photo the
trip's **name** and its **dates and length** ("12–19 Mar 2026 · 8 days"). Nothing is drawn over
the photo but the badge. No footer, no counts, no destination line, no extra request per card. A button "New trip" ends the Upcoming list.

**A trip is named after its destination** (the country, region or city chosen), never with its
length: "Austria", not "Austria, 8 days".

### Create new trip (screen 13)

Back, then the title "Create new trip" and one line of subtitle. Then, as hairline fields:

1. **Destination:** a pin icon, the search field (a city or area in an imported region), results as
   hairline rows with the reason when one cannot be chosen. Once chosen, the name with its kind and
   country, an X to clear it, and the destination's cover illustration beneath.
2. **Start date** (optional) and **Duration** (days, with minus and plus) side by side. The start
   date opens a **month calendar** in a sheet (Monday first, today ringed, "Clear the date"); a date
   is chosen, never typed.
3. **Travel style:** Relaxed, Balanced, Active (chips).
4. **Public transport:** a switch.
5. A line: travel style and public transport are saved for later; the plans do not use them yet.
6. Two buttons:
   - **Generate itineraries** (dark): creates the trip and the two proposals to compare.
   - **Start with an empty trip** (outlined): creates the trip and an empty plan, one empty day
     per trip day, chosen as its itinerary at once. No proposals. The trip opens on its overview.

Removed from the screen of the reference image: interests, budget and "Include popular
highlights", the "Change photo" control and the personalised-itineraries note. The trip name is
not asked; it is the destination.

### Trip overview (screens 02, 12)

- **Header, then cover.** Above the photo: Back, the trip's **name and its dates and length**
  centred, and the trip menu. Nothing else (no status, no destination line). The cover follows,
  with nothing over it.
- **A white sheet curves over the cover's lower edge** and holds the tabs: Overview, Itinerary,
  Map, Photos, Documents. The tabs stay at the top when the page scrolls. Overview and Itinerary
  share this layout; only Map gives up the cover.
- **Overview tab:** three flat figures, **cities, places, restaurants** (no number of days: the
  header says it); then "Your itinerary" with its kind, a sentence, the headline facts and two
  buttons, Itinerary and Map. Nothing else: no first days, no notes and reservations block.
- **Itinerary tab (screen 12):** the same header, cover and tabs as Overview, then the trip's days
  as a **timeline**: a dot on a thin rail, a small illustrated
  thumbnail, "Day 3 · Wed 14 Mar", the town, "4 activities · 2 restaurants". A day opens the **Map
  tab on that day**.
- **Map tab (screens 03, 14):** a compact header (Back, the name, the menu) and the tabs, then the
  map of the day, then **the day pills**, then the day's stops. It uses the whole screen.
- **Photos:** a planned feature.
- **Documents (screens 15, 16, ADR 023):** see "Documents" below.

### The day: map and stops (screens 03, 12)

- **The stops get most of the height.** The map is the smaller part (about a third of the space
  between the tabs and the bottom bar), the stops the larger. The map's camera fits the day's stops.
- **Day pills sit under the map, above the stops** (screen 14): rounded pills that share the width
  (and scroll sideways when there are many days), the chosen one dark with white text. "Day 1" over
  "Thu, 12 Mar", or just "Day 1" when the trip has no dates; the text is **centred** in every pill.
- **No day title above the stops.** The pills say which day it is; there is no "Day 3, Wed 14 Mar,
  8 visits, 2 meals, 4 h at the sights, 1 h travelling" block. A trip
  that moves between base cities shows the day's base city as one quiet line.
- **A stop is a hairline row:** the time (start over end), a numbered disc that matches the map
  marker, the name in small bold, the **kind icon** and the kind and length in caption ("Attraction ·
  2 h", "Lunch · Restaurant · 1 h"), a chevron to the place's details. The names are English where
  the source has an English name; the local name is on the place's details. Selecting a stop tints its row, highlights
  its marker, and expands the reasons it is in the plan with Lock and Remove.
- **Travel between stops** is one muted caption line with its Routed or Estimated tag.
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

Each marker keeps a 48 dp touch area around the drawn shape. The map key and attribution stay.

### Place detail (screen 04)

Cover (only the Back button over it); under it the kind icon and word, the name and, when the plan
shows an English name, the local name; when, how long, where; opening hours "Not checked" for sights (ADR 003); for
places to eat the meal, venue and cuisine from the data; the reasons it is in the plan; the data
source. **Facts are separated by hairlines, not placed in cards.** No rating, price or description:
the data has none (CLAUDE.md rule 5).

### Proposals (screen 14)

"Choose your itinerary", a sentence ("We've created two options for your 2-day trip to Salzburg…"),
the dates and length, then **the two plans as cards**: the cover, a badge ("Best-known sights",
"More variety"), the name ("Classic Salzburg", "Salzburg & beyond", from fixed templates),
"The essentials" / "A wider experience", the profile's sentence, then places, restaurants and
travel time from the plan's own numbers, and two buttons: **View details** (outlined) and **Choose
this itinerary** (dark). A **Compare itineraries** row opens the comparison table; "You can always
adjust your itinerary later" ends the page. After new proposals were asked for, the plan chosen
earlier is kept apart with a note. **View details** opens that plan's map with the day pills under
it and the stops below, and "Choose this itinerary" under them. Not built from the mock: a
"Recommended" badge (nothing says one plan is better), city count and "Mostly walking" (a summary
has neither), "Add to Day 1" (a proposal is not edited).

### Add (screens 05, 06)

Add is contextual. On a trip: Place and Restaurant, with up to three suggested days or meal slots
from the recalculation, each a hairline row with its reasons; the preview shows the diff before
anything changes. Outside a trip it starts a new trip.

### Documents (screens 15, 16)

- **The tab, empty:** an illustration, "No documents yet", a sentence, **one tile per kind**
  (Tickets, Bookings, Transport, Insurance, Other documents, each with what belongs there) that
  starts adding that kind, "Add a document" (dark) and the line that documents stay on this phone.
- **The tab, with documents:** filter chips (All and the five kinds), "All documents" with **Sort**
  (newest, oldest, title), then rows: a tinted tile for the kind (`docTones`), the title, "Ticket ·
  PDF · 245.0 kB", the document's date (or what it is about), a thumbnail for a picture, and a "…"
  menu (Open, Edit).
- **Add document, step one:** "Upload from device" (the system file picker: PDFs and pictures, and
  Google Drive through Android's picker), "Take a photo", "Add a link", "or create manually",
  "Create a document", and a "Your documents stay private" note. Only the first works; the others
  are disabled and say "Coming later".
- **Add document, step two:** the file with its picture or tile and "Replace file"; **Document
  type** chips; **Title** (filled from the file name); **Related to**: Whole trip, A day (day chips),
  A place (the plan's stops) or A journey (each day that starts at a new base city); **Date**
  (optional, the calendar); **Notes** (optional, 500 characters, with a counter). "Save document" is
  disabled until a file, a title, a type and a complete link are chosen. No "Make available offline"
  switch: every document is already on the phone.
- **A document:** its title, its kind as a tile and badge, a picture in place for images, then
  hairline facts (About, File, Type and size, Date and Notes when set, Added). Open (dark, the
  phone's viewer), Edit (outlined), Delete (plain text, asks first).
- **A place's details** list that place's documents under "Tickets and documents" (sights) or
  "Bookings and documents" (places to eat), with "Attach a document".
- **A past trip** has a Documents button that opens the same list.

### Photos, Explore, More (screens 07, 10, 11)

Planned features and a menu of hairline rows. Items that are not built say "Coming later".

## 5. Plans and times

- **Meals are aimed at lunch 13:00 and dinner 20:00** (owner, 2026-11-14). Windows: lunch 13:00 to
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

- **Adding places to an empty trip.** An empty trip is a manual plan. The Add-place and Add-a-
  restaurant flows (ADR 018, 019) recalculate planned itineraries and refuse a manual one
  ("not recalculable"). Adding a place to an empty day by hand needs its own flow: choose the day,
  say how long to stay (a manual item has no default length), and place it by hand. It needs the
  owner's approval and an amendment to ADR 021 before it is built.
- **Travel style and public transport** are stored nowhere. Using them needs a field on the trip
  and a rule in the planner, with an ADR.
- **"Change photo"** (ADR 022, step 4) is not built.
- **English names** exist only where OpenStreetMap has `name:en`; the rest keep their local name.
  Wikidata labels would fill more gaps but need an ADR for the provider.
- **Notes, reservations, trip summary:** ADR 021, "Not built". Documents are built (ADR 023) and
  are kept on the phone only; backing them up would need accounts or an export.
- **Dark mode** is not designed.
