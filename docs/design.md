# Detour design

How the mobile app looks and behaves. It is the working reference for screens: build to it, and
change it in the same change as the screens (CLAUDE.md, "Update the affected documents").

- **Sources:** the reference screens in [`screenshots/`](screenshots/) (01 to 13), the app as built
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
4. **Illustrated covers, no invented photos.** Destinations get a generated illustration until
   ADR 022 (proposed) is accepted and built; then a real photo (Wikimedia Commons, with its credit)
   replaces the illustration wherever the source has one, and the illustration stays as the fallback.
   The "Change photo" control of screen 13 is not built yet; ADR 022, decision 15, describes it. A
   photo is never shown without its author and licence, and never as a map marker.
5. **Honest about what is not built.** A control that does nothing yet says so in words
   ("Not built yet", "saved for later"). Nothing is faked.
6. **Small type, large targets.** Body text is compact; every control is still at least 48 dp tall
   (the accessibility test enforces it, using height plus hit slop).

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
cover illustration, the status badge at the top right, the trip's **name**, its **dates and length**
("12–19 Mar 2026 · 8 days") over the lower edge. No footer, no counts, no destination line, no
extra request per card. A button "New trip" ends the Upcoming list.

**A trip is named after its destination** (the country, region or city chosen), never with its
length: "Austria", not "Austria, 8 days".

### Create new trip (screen 13)

Back, then the title "Create new trip" and one line of subtitle. Then, as hairline fields:

1. **Destination:** a pin icon, the search field (a city or area in an imported region), results as
   hairline rows with the reason when one cannot be chosen. Once chosen, the name with its kind and
   country, an X to clear it, and the destination's cover illustration beneath.
2. **Start date** (optional) and **Duration** (days, with minus and plus) side by side.
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

- **Cover** (illustration) with Back and the trip menu, the status, the name, the dates and the
  destination.
- **A white sheet curves over the cover's lower edge** and holds the tabs: Overview, Itinerary,
  Map, Photos, Documents. The tabs stay at the top when the page scrolls.
- **Overview tab:** three flat figures, **cities, places, restaurants** (no number of days: the
  header says it); then "Your itinerary" with its kind, a sentence, the headline facts and two
  buttons, Itinerary and Map. Nothing else: no first days, no notes and reservations block.
- **Itinerary tab (screen 12):** no cover. A compact header (Back, the trip's name, the menu), the
  tabs, then the trip's days as a **timeline**: a dot on a thin rail, a small illustrated
  thumbnail, "Day 3 · Wed 14 Mar", the town, "4 activities · 2 restaurants". A day opens the **Map
  tab on that day**.
- **Map tab (screen 03):** the same compact header, a day strip, the map of the day, and the day's
  stops beneath it.
- **Photos, Documents:** planned features.

### The day: map and stops (screens 03, 12)

- **The stops get most of the height.** The map is the smaller part (about a third of the space
  between the tabs and the bottom bar), the stops the larger. The map's camera fits the day's stops.
- **No day title above the stops.** The strip above says which day it is ("Day 3" over "14 Mar");
  there is no "Day 3, Wed 14 Mar, 8 visits, 2 meals, 4 h at the sights, 1 h travelling" block. A trip
  that moves between base cities shows the day's base city as one quiet line.
- **A stop is a hairline row:** the time (start over end), a numbered disc that matches the map
  marker, the name in small bold, the kind and length in caption ("Attraction · 2 h", "Lunch ·
  Restaurant · 1 h"), a chevron to the place's details. Selecting a stop tints its row, highlights
  its marker, and expands the reasons it is in the plan with Lock and Remove.
- **Travel between stops** is one muted caption line with its Routed or Estimated tag.
- **Type sizes here are small** (name 14, details 13) so more stops show at once.

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

Cover, kind and name; when, how long, where; opening hours "Not checked" for sights (ADR 003); for
places to eat the meal, venue and cuisine from the data; the reasons it is in the plan; the data
source. **Facts are separated by hairlines, not placed in cards.** No rating, price or description:
the data has none (CLAUDE.md rule 5).

### Add (screens 05, 06)

Add is contextual. On a trip: Place and Restaurant, with up to three suggested days or meal slots
from the recalculation, each a hairline row with its reasons; the preview shows the diff before
anything changes. Outside a trip it starts a new trip.

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
- **Destination and attraction photos and "Change photo"**: ADR 022, proposed, not built. Open until
  the Wikimedia terms are read and a coverage spike is done.
- **Documents, notes, reservations, trip summary:** ADR 021, "Not built".
- **Dark mode** is not designed.
