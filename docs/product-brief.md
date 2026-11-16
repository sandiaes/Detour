# Product brief

## 1. Summary

Detour is a mobile **trip manager and travel history** (ADR 026, owner decision of 2026-11-14).
The user creates a trip, usually empty, fills it with places, restaurants and documents, keeps it
while it happens and keeps it afterwards as a record of what was done on which day. As an optional
helper the app can **suggest** two clearly different sightseeing itineraries for a destination and
a length, and keeps such a plan coherent as places are added. Suggestions contain attractions only;
restaurants and cafés are always added by the user. Planning is deterministic: no language model is
used at runtime.

> **ADR 026 is proposed; all six of its build steps are built** (planner, data, history, app) and
> await acceptance. Destinations (ADR 027) and trip export and import (ADR 028) are built;
> Optimize (ADR 029) is built too.

First platform: Android. The architecture must allow an iPhone version without a rewrite.

## 2. Target user

A traveller who plans their own leisure trips of roughly 2 to 14 days, mostly by hand, and wants
one place for the trip while it is planned and lived and a record of it afterwards. Suggested
sightseeing plans are an occasional help, not the main way in.

## 3. Product goals and how each is met

| # | Goal | Approach | Release |
|---|---|---|---|
| 0 | **A trip manager and history** (ADR 026): empty trips filled by hand, documents, past trips kept with their days | Empty trip as the main way in; past trips keep a day-by-day record (ADR 006 amendment) | Core; history built in steps |
| 1 | Destination or area plus duration as input | Search over an imported gazetteer of cities and areas; duration in days. Any place can be a destination as an empty trip (ADR 027) | MVP; outside regions built |
| 2 | *Optional:* at least two meaningfully different suggested itineraries | Two strategy profiles of one engine plus a diversity check; frozen, maintained | MVP |
| 3 | Suggested itineraries include cities or areas, attractions, travel times, visit durations. **No restaurants or cafés (ADR 026)** | Imported open data; routed walking and driving times; category-based visit durations; one unplanned midday gap a day | MVP, except public transport |
| 3 | Public transport when relevant | **Transport legs entered by hand** (mode, from, to, day, start, length or unknown, note; ADR 032, built 2026-11-16). Schedule-based transit legs remain after the MVP (Phase 10, not started) | Manual legs built; routing after MVP |
| 4 | Add a city or location not in the proposal | Search or map pin; becomes a mandatory visit | MVP |
| 5 | Automatic recalculation around the addition | Re-plan with minimal disruption; user reviews a diff | MVP |
| 6 | Add a restaurant manually | Search through Photon (or your saved places), or manual entry with a name, a kind and a pin (ADR 026; no imported restaurants) | MVP |
| 7 | ~~Best day and time for that restaurant~~ | **Retired (ADR 026):** the user chooses the day and time; the Phase 8 slot engine is removed | Retired |
| 8 | ~~Restaurants categorised by cuisine, meal type~~ | **Removed (ADR 026):** a restaurant is a name, a point and a kind (restaurant or café); Photon supplies no cuisine | Removed |
| 9 | User-defined expected price or budget | **Removed for now** (owner, 2026-11-13; ADR 017): no budgets, currencies or prices | — |
| 0b | **Optimize a hand-made trip** (ADR 029, accepted and built; third manager feature): the engine proposes a new order of the user's stops, within each day or across days, for the least travel; locked and ticketed stops stay, restaurants move at most 60 minutes and never start after 21:00 | Reorder search from the sequencer, travel times through the adapter, a preview with the saving, an undo | Built 2026-11-15, awaits acceptance |
| 10 | Store travel photos linked to trip, day, city or item | **Partly built (ADR 031):** a trip links its own photo albums (opened in Google Photos) and can take a cover from the phone; photos by day, city or item are not built | Future (core to the history, owner's order) |
| 11 | No LLM at runtime | Deterministic engine, reason codes, fixed templates | Always |
| 12 | Free or open APIs preferred | Open data imported and self-hosted; a few free public services behind adapters | Always |
| 13 | See past trips on a map | Archive of visited cities and attractions, no routing (ADR 006) | Built 2026-11-13, awaits acceptance |

## 4. Core user flows

1. **Create a trip.** Choose a destination (a city or an area) from search results, set the number
   of days and optionally a start date, then **start with an empty trip** (the main button, ADR 026)
   or ask for suggested itineraries. An area is planned from base cities with the days divided
   between them (ADR 016); areas in Japan are planned as single cities for now (D4). The empty trip is the main button; suggested itineraries are the second
   (ADR 026).
2. **Compare proposals (optional).** See two itineraries side by side with a short structured summary of
   how they differ (cities covered, number of visits, total travel time). Open either on the
   map or as a day list. Select one: it opens, and from then on the trip opens on that plan, not
   on the proposals (ADR 020). "Trip settings" asks for new proposals (the chosen plan stays
   selected until another is chosen) or deletes the trip.
3. **Review a day.** Ordered visits, with sights and places to eat told apart on the
   map and in the list (ADR 020), with start times and durations, transfers with mode
   and duration, markers for estimated travel times and, on an area trip, the day's base city and
   the drive from the previous one. A suggested day has one unplanned "Free time" gap at midday
   (ADR 026, built).
4. **Add a place.** Search or drop a pin. The app shows what would change. Accept or discard.
5. **Add a restaurant or café.** Search through Photon, or enter it by hand (a name, a map pin or
   typed coordinates, and the kind). The user chooses the day and the start time; the length is a
   default they can change. No cuisine and no served meals are stored: Photon does not supply them
   (ADR 026, built: the imported restaurants and the slot suggestions of ADR 019 are gone).
6. **Optimize (ADR 029).** On a trip with at least three stops, ask the engine for a shorter
   order. Choose to reorder within each day or across all days, keep the stops with tickets in place,
   review the diff and the saving, apply or discard. Never longer than the current plan; opening
   hours are not known and the preview says so.
7. **Export and import (ADR 028).** A trip menu, a past trip and More offer a `.detour` file with the
   trip (the chosen plan, or a past trip's record) and, if wanted, its documents; "Back up all
   trips" puts every trip in one file. The file goes to the system share sheet and Detour uploads
   nothing. "Import a trip" adds a file's trips as new copies, so a reinstall or a new phone keeps
   the history. Documents in the file are not encrypted; the app says so.
8. **Look back.** A past trip keeps its days, places, visited marks and documents, and the map of
   the cities and attractions visited (ADR 006 amended by ADR 026). Since 2026-11-16 a past trip keeps its
   whole plan and works like an upcoming one (ADR 006 amendment); only its undo history is cut to five. Built: a past trip's Days tab lists its stops by
   day with their times.

## 5. What "meaningfully different" means

Two proposals are different enough when either holds:

- their sets of visits overlap by no more than a set threshold (proposed: Jaccard similarity at
  most 0.6), or
- they cover a different set of cities or allocate days to cities differently.

When a destination cannot support two distinct plans, the app says so and shows one.

## 6. Restaurant information

A restaurant or café is something the user adds (ADR 026). It is stored as what is known:

| Attribute | Source | Shown when missing |
|---|---|---|
| Name | Photon result or typed | Required |
| Location | Coordinates (Photon or a pin) | Always present |
| Kind | `restaurant` or `cafe`: Photon's `amenity` value, or the user's choice | Required |
| Address | Photon, when it has one | Not shown |
| Cuisine, served meals | **Not provided** (Photon has none; removed by ADR 026) | Not shown |
| Price level, rating | **Not provided** (ADR 017; never from third parties) | Not shown |

Free and open sources do not carry trustworthy restaurant prices, ratings or cuisines in the
shape Detour needs. The product shows only what it can stand behind.

**No meals in a suggested plan** (ADR 026, superseding the meal part of ADR 016). Generated
itineraries have no lunch, no dinner and no snack. Each day has one unplanned midday gap
(*proposed:* 90 minutes between 12:30 and 14:00) and runs 09:00 to 20:00 (*proposed*). Built
(`planner-3.0.0`); the earlier fixed meal windows of ADR 016 are history.

**No prices, budgets or currencies** (ADR 017, owner decision of 2026-11-13). Earlier versions of
this brief had a trip currency, a meal budget per person, user-entered prices and price bands;
they are removed for now and need a new ADR to return.

## 7. Data transparency rules

- Every travel time is labelled routed or estimated.
- Every visit duration is a default that the user can change.
- Opening hours are not used (ADR 003). The app does not know whether a place is open and does
  not warn about closed places.
- No price is shown: the app has none (ADR 017).
- Every placement decision can show its reasons.

## 8. Out of scope

Permanently, under the current brief:

- booking, payments, hotel availability, flight-price comparison
- any LLM or generative-AI dependency
- restaurant ratings or reviews from third parties
- imported restaurant, café or cuisine data (ADR 026)

Not in the MVP (see `docs/app-plan.md` for the phase each belongs to):

- computed public-transport legs and real-time transit data (legs the user enters by hand are built:
  ADR 032)
- iOS build
- photos inside Detour (a trip links its own Google Photos albums, which open in Google Photos, and its
  cover can be a picture from the phone: ADR 031; showing the photos themselves is not built)
- weather
- suggestions for destinations outside the imported pilot regions (trips there are empty, ADR 027)
- user accounts, sharing and multi-device sync (a trip can be exported and imported as a file, ADR 028)
- offline map downloads
- public-holiday opening rules

## 9. Assumptions to confirm

| Assumption | Why it matters |
|---|---|
| The MVP serves imported pilot regions: Japan, Italy, Austria, Czechia and Hungary | Decided (D2) |
| The app is open source and non-commercial | Decided (D1) |
| One anonymous installation per device is enough | Approved (D5) |
| Day start and end points are not tied to accommodation | Hotels are out of scope; days start at the first item |
| Walking and driving are sufficient for the MVP | Approved (D4); weakest for multi-city trips in Japan |

## 10. Success criteria

Defined in `docs/kpis.md`. In short: a trip created and filled quickly by hand; past trips kept
with their days; where itineraries are suggested, two distinct, feasible sightseeing plans within
seconds; additions handled without breaking the plan; zero spend on external APIs.
