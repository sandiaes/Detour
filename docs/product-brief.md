# Product brief

## 1. Summary

Detour is a mobile travel-itinerary planner. The user names a destination or area and a trip
length; the app proposes at least two clearly different itineraries, then keeps the plan
coherent as the user adds places and restaurants. Planning is deterministic: no language model
is used at runtime.

First platform: Android. The architecture must allow an iPhone version without a rewrite.

## 2. Target user

A traveller planning a leisure trip of roughly 2 to 14 days who wants a workable day-by-day
plan quickly and expects to adjust it.

## 3. Product goals and how each is met

| # | Goal | Approach | Release |
|---|---|---|---|
| 1 | Destination or area plus duration as input | Search over an imported gazetteer of cities and areas; duration in days | MVP |
| 2 | At least two meaningfully different itineraries | Two strategy profiles of one engine plus a diversity check | MVP |
| 3 | Itineraries include cities or areas, attractions, restaurants, transport options, travel times, visit durations | Imported open data; routed walking and driving times; category-based visit durations | MVP, except public transport |
| 3 | Public transport when relevant | Schedule-based transit legs | After MVP (Phase 10) |
| 4 | Add a city or location not in the proposal | Search or map pin; becomes a mandatory visit | MVP |
| 5 | Automatic recalculation around the addition | Re-plan with minimal disruption; user reviews a diff | MVP |
| 6 | Add a restaurant manually | Search local data, then external search, then manual entry | MVP |
| 7 | Best day and time for that restaurant | Scored over every day and meal slot: location, neighbouring activities, meal time, travel impact | MVP |
| 8 | Restaurants categorised by cuisine, meal type, location, suitability | Cuisine, venue and meal type from open data; suitability computed. No price level (ADR 017) | MVP |
| 9 | User-defined expected price or budget | **Removed for now** (owner, 2026-11-13; ADR 017): no budgets, currencies or prices | — |
| 10 | Store travel photos linked to trip, day, city or item | Data model reserved; on-device first | Future |
| 11 | No LLM at runtime | Deterministic engine, reason codes, fixed templates | Always |
| 12 | Free or open APIs preferred | Open data imported and self-hosted; a few free public services behind adapters | Always |
| 13 | See past trips on a map | Archive of visited cities and attractions, no routing (ADR 006) | Built 2026-11-13, awaits acceptance |

## 4. Core user flows

1. **Create a trip.** Choose a destination (a city or an area) from search results, set the number
   of days and optionally a start date. An area is planned from base cities with the days divided
   between them (ADR 016); areas in Japan are planned as single cities for now (D4).
2. **Compare proposals.** See two itineraries side by side with a short structured summary of
   how they differ (cities covered, number of visits, total travel time). Open either on the
   map or as a day list. Select one: it opens, and from then on the trip opens on that plan, not
   on the proposals (ADR 020). "Trip settings" asks for new proposals (the chosen plan stays
   selected until another is chosen) or deletes the trip.
3. **Review a day.** Ordered visits and meals, with sights and places to eat told apart on the
   map and in the list (ADR 020), with start times and durations, transfers with mode
   and duration, markers for estimated travel times, the meal's venue type and cuisine, and, on an
   area trip, the day's base city and the drive from the previous one.
4. **Add a place.** Search or drop a pin. The app shows what would change. Accept or discard.
5. **Add a restaurant.** Search the map data, then the wider search, or enter it by hand (a name,
   a map pin or typed coordinates; cuisines and the meals it serves are optional). The app proposes
   the best day and meal slot with reasons, the estimated detour and which items move, and lists two
   alternatives. Accept, pick an alternative, or limit the suggestions to a day or meal. The meal
   always stays inside its meal window and the day inside its hours (built in Phase 8, ADR 019).

## 5. What "meaningfully different" means

Two proposals are different enough when either holds:

- their sets of visits overlap by no more than a set threshold (proposed: Jaccard similarity at
  most 0.6), or
- they cover a different set of cities or allocate days to cities differently.

When a destination cannot support two distinct plans, the app says so and shows one.

## 6. Restaurant information

| Attribute | Source | Shown when missing |
|---|---|---|
| Cuisine | OpenStreetMap `cuisine` tag, normalised | "Cuisine not specified" |
| Venue and meal type | Venue tag | Derived from venue type alone |
| Location | Coordinates | Always present |
| Price level | **Not provided** (ADR 017: no prices for now) | Not shown |
| Suitability for the itinerary | Computed | Always present, with reasons |
| Rating | **Not provided** | Not shown |

Free and open sources do not carry trustworthy restaurant prices or ratings. The product shows
only what it can stand behind.

**Meals in a plan** (ADR 016) sit in fixed windows: breakfast 07:30–10:00, lunch 12:00–14:30,
afternoon snack 15:00–17:30, dinner 18:30–21:00. A place to eat is chosen near the visits before
and after the meal, varying cuisines, and only among places whose venue type serves that meal.

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

Not in the MVP (see `docs/app-plan.md` for the phase each belongs to):

- public transport legs and real-time transit data
- iOS build
- photos
- weather
- destinations outside the imported pilot regions
- user accounts, sharing and multi-device sync
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

Defined in `docs/kpis.md`. In short: two distinct, feasible itineraries within seconds;
additions handled without breaking the plan; restaurant placement that users accept; zero
spend on external APIs.
