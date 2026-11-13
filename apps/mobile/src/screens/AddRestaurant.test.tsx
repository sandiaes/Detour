import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeChangeSet,
  makeItinerary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { __mock as maplibre } from "../testing/maplibreMock";
import { RESTAURANT_DEBOUNCE_MS } from "./AddRestaurantScreen";

beforeEach(() => {
  jest.useFakeTimers();
  maplibre.reset();
});
afterEach(() => jest.useRealTimers());

const planRoute = {
  name: "itinerary",
  tripId: TRIP_ID,
  itineraryId: ESSENTIALS_ID,
  view: "days",
  day: 1,
} as const;

const POST = {
  id: "00000000-0000-4000-8000-00000000ac01",
  name: "Zur Alten Post",
  kind: "restaurant",
  category: "restaurant",
  lat: 48.22,
  lon: 16.38,
  region_id: "austria",
  city_id: 900101,
  city_name: "Vienna",
  cuisines: ["austrian", "regional"],
  venue_type: "restaurant",
  meal_types: ["dinner", "lunch"],
  distance_m: 900,
};

const NO_CUISINE = {
  ...POST,
  id: "00000000-0000-4000-8000-00000000ac02",
  name: "Café Stumm",
  cuisines: null,
  venue_type: "cafe",
  meal_types: ["breakfast", "snack"],
};

const NOT_EXTERNAL = { state: "not_requested", provider: null, results: [] };

function slot(rank: number, day: number, meal: string, start: string, end: string, extra = {}) {
  return {
    rank,
    day,
    meal_type: meal,
    start_time: start,
    end_time: end,
    after_item_id: `after-${rank}`,
    after_name: "Belvedere",
    before_name: rank === 3 ? null : "Albertina",
    travel_minutes_added: rank * 2,
    travel_label: "estimated",
    detour_metres: 300 * rank,
    replaces: rank === 1 ? "Gasthaus Zum Test" : null,
    items_moved:
      rank === 1
        ? []
        : [
            {
              kind: "visit",
              name: "Albertina",
              old_start_time: "13:00:00",
              new_start_time: "13:40:00",
            },
          ],
    reasons: [
      {
        code: "SLOT_WINDOW",
        text: `${meal} is planned between 13:00 and 15:00; here it runs ${start}-${end}.`,
      },
      { code: "SLOT_TRAVEL", text: `Day ${day} travel changes by +${rank * 2} min (estimated).` },
    ],
    score: 100 * rank,
    ...extra,
  };
}

const SUGGESTIONS = {
  restaurant: {
    name: "Zur Alten Post",
    venue_type: "restaurant",
    cuisines: ["austrian", "regional"],
    meal_types: ["dinner", "lunch"],
    meal_types_basis: "venue_type",
  },
  suggestions: [
    slot(1, 1, "lunch", "12:15:00", "13:15:00"),
    slot(2, 2, "dinner", "18:30:00", "20:00:00"),
    slot(3, 3, "lunch", "12:00:00", "13:00:00"),
  ],
  slots_considered: 6,
  issues: [],
};

function server(over: Record<string, (c: never) => unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "GET /v1/restaurants/search": () => ({
      query: "alte",
      results: [POST, NO_CUISINE],
      your_places: [],
      external: NOT_EXTERNAL,
    }),
    "POST /v1/itineraries/{itinerary_id}/restaurant-suggestions": () => SUGGESTIONS,
    "POST /v1/itineraries/{itinerary_id}/change-sets": () =>
      makeChangeSet({ action: "add_restaurant", target_name: "Zur Alten Post" }),
    "GET /v1/change-sets/{change_set_id}": () =>
      makeChangeSet({ action: "add_restaurant", target_name: "Zur Alten Post" }),
    "POST /v1/change-sets/{change_set_id}/apply": () => ({
      change_set: makeChangeSet({ action: "add_restaurant", status: "applied", result_version: 2 }),
      itinerary: makeItinerary("essentials", { version: 2 }),
    }),
    "POST /v1/user-places": (c: { body: Record<string, unknown> }) => ({
      id: "00000000-0000-4000-8000-00000000cc09",
      ...c.body,
    }),
    "PATCH /v1/user-places/{place_id}": (c: { params: { place_id: string }; body: object }) => ({
      id: c.params.place_id,
      ...c.body,
    }),
    ...over,
  } as never);
}

async function openScreen(client = server()) {
  await render(
    <Harness client={client} initial={planRoute}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByTestId("add-restaurant"));
  expect(await screen.findByText("Add a restaurant")).toBeOnTheScreen();
  return client;
}

async function search(text: string) {
  await fireEvent.changeText(screen.getByLabelText("Restaurant name"), text);
  await act(async () => {
    jest.advanceTimersByTime(RESTAURANT_DEBOUNCE_MS + 10);
  });
}

test("search the map data, see three slots with reasons, preview, accept", async () => {
  const client = await openScreen();
  await search("alte");
  expect(client.calls.find((c) => c.path === "/v1/restaurants/search")?.params).toMatchObject({
    q: "alte",
    lat: 48.2082,
  });
  // What the data states, and what it does not.
  expect(
    screen.getByText(/Austrian, regional · Restaurant · Lunch, Dinner · Vienna/),
  ).toBeOnTheScreen();
  expect(
    screen.getByText(/Cuisine not specified · Café · Breakfast, Afternoon snack · Vienna/),
  ).toBeOnTheScreen();

  await fireEvent.press(screen.getByLabelText(/Zur Alten Post, Austrian/));
  await fireEvent.press(screen.getByTestId("find-slots"));
  expect(client.calls.find((c) => c.path.endsWith("/restaurant-suggestions"))?.body).toEqual({
    place_id: POST.id,
  });
  expect(await screen.findByText(/Day 1 · Lunch · 12:15–13:15/)).toBeOnTheScreen();
  expect(screen.getByText(/Day 2 · Dinner · 18:30–20:00/)).toBeOnTheScreen();
  expect(screen.getByText(/Day 3 · Lunch · 12:00–13:00/)).toBeOnTheScreen();
  // Reasons, the estimated detour, and which items move are on every card.
  expect(screen.getAllByText("Why here")).toHaveLength(3);
  expect(screen.getByText("+2 min travel that day (estimated)")).toBeOnTheScreen();
  expect(screen.getByText("Replaces Gasthaus Zum Test, planned for this meal")).toBeOnTheScreen();
  expect(screen.getAllByText("Albertina: 13:00 → 13:40")).toHaveLength(2);
  // The best slot is marked in words.
  expect(screen.getAllByText("Best")).toHaveLength(1);
  expect(screen.getAllByText(/travel changes by/).length).toBe(3);
  // Nothing is stored or changed by asking.
  expect(client.count("POST /v1/itineraries/{itinerary_id}/change-sets")).toBe(0);

  // The best slot is chosen already; pick the second one instead.
  await fireEvent.press(screen.getByLabelText("Alternative: Day 2 · Dinner · 18:30–20:00"));
  await fireEvent.press(screen.getByTestId("preview-slot"));
  expect(client.calls.find((c) => c.path.endsWith("/change-sets"))?.body).toEqual({
    action: "add_restaurant",
    place_id: POST.id,
    day: 2,
    meal_type: "dinner",
    after_item_id: "after-2",
  });
  expect(await screen.findByText("Add Zur Alten Post?")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("accept-change"));
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(1);
  expect(await screen.findByText("Essentials plan")).toBeOnTheScreen();
});

test("a restaurant entered by hand without a cuisine stays 'Cuisine not specified'", async () => {
  const client = await openScreen(
    server({
      "POST /v1/itineraries/{itinerary_id}/restaurant-suggestions": () => ({
        ...SUGGESTIONS,
        restaurant: {
          name: "Mein Lokal",
          venue_type: null,
          cuisines: null,
          meal_types: null,
          meal_types_basis: "unknown",
        },
      }),
    }),
  );
  await fireEvent.press(screen.getByTestId("hand-mode"));
  expect(screen.getByTestId("find-slots")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Name of the restaurant"), "Mein Lokal");
  // Typed coordinates (a decimal comma is accepted); an out-of-range value is refused.
  await fireEvent.changeText(screen.getByLabelText("Latitude"), "91");
  expect(screen.getByText(/A number from −90 to 90/)).toBeOnTheScreen();
  expect(screen.getByTestId("find-slots")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Latitude"), "48,2101");
  await fireEvent.changeText(screen.getByLabelText("Longitude"), "16.3702");
  expect(screen.getByText(/the meals it serves are not specified/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("find-slots"));

  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "restaurant",
    name: "Mein Lokal",
    lat: 48.2101,
    lon: 16.3702,
    source: "manual_pin",
  }); // no cuisines, no meal types: unknown, never invented
  expect(client.calls.find((c) => c.path.endsWith("/restaurant-suggestions"))?.body).toEqual({
    user_place_id: "00000000-0000-4000-8000-00000000cc09",
  });
  expect(await screen.findByText("Cuisine not specified · Meals not specified")).toBeOnTheScreen();
});

test("tapping the map fills in the coordinates, and cuisines and meals are sent when given", async () => {
  const client = await openScreen();
  await fireEvent.press(screen.getByTestId("hand-mode"));
  await fireEvent.changeText(screen.getByLabelText("Name of the restaurant"), "Trattoria");
  await act(async () => {
    maplibre.map?.onPress({ nativeEvent: { lngLat: [16.4, 48.21] } });
  });
  expect(screen.getByLabelText("Latitude")).toHaveProp("value", "48.210000");
  await fireEvent.changeText(screen.getByLabelText("Cuisine (optional)"), "Italian, pizza");
  await fireEvent.press(screen.getByLabelText("Dinner"));
  await fireEvent.press(screen.getByTestId("find-slots"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "restaurant",
    name: "Trattoria",
    lat: 48.21,
    lon: 16.4,
    cuisines: ["italian", "pizza"],
    meal_types: ["dinner"],
    source: "manual_pin",
  });
  // Asking again after a change updates the same place instead of saving a second one.
  await fireEvent.changeText(screen.getByLabelText("Cuisine (optional)"), "Greek");
  await fireEvent.press(await screen.findByTestId("find-slots"));
  expect(client.count("POST /v1/user-places")).toBe(1);
  expect(client.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
    cuisines: ["greek"],
  });
});

test("nothing local: a wider search offers restaurants with the venue rule's meals", async () => {
  const client = await openScreen(
    server({
      "GET /v1/restaurants/search": (c: { params: Record<string, unknown> }) => ({
        query: "Hütte",
        results: [],
        your_places: [],
        external: c.params.include_external
          ? {
              state: "ok",
              provider: "photon",
              results: [
                {
                  provider: "photon",
                  ref: "N42",
                  name: "Alm Hütte",
                  lat: 47.5,
                  lon: 13.1,
                  city: "Hallstatt",
                  state: null,
                  country: "Austria",
                  venue_type: "restaurant",
                  meal_types: ["dinner", "lunch"],
                  meal_types_basis: "venue_type",
                  cuisines: null,
                },
              ],
            }
          : NOT_EXTERNAL,
      }),
    }),
  );
  await search("Hütte");
  expect(
    await screen.findByText("Nothing in the imported data matches “Hütte”."),
  ).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Search more widely"));
  await fireEvent.press(await screen.findByLabelText(/Alm Hütte, Cuisine not specified/));
  // The venue rule's meals are the starting point, and the user can change them.
  expect(screen.getByLabelText("Lunch")).toBeSelected();
  expect(screen.getByLabelText("Dinner")).toBeSelected();
  expect(screen.getByLabelText("Breakfast")).not.toBeSelected();
  await fireEvent.press(screen.getByTestId("find-slots"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "restaurant",
    name: "Alm Hütte",
    lat: 47.5,
    lon: 13.1,
    meal_types: ["lunch", "dinner"],
    source: "search_result",
    search_provider: "photon",
    search_ref: "N42",
  });
});

test("when the outside search is used up, entering by hand still works", async () => {
  await openScreen(
    server({
      "GET /v1/restaurants/search": () => ({
        query: "Nirgends",
        results: [],
        your_places: [],
        external: { state: "budget_exhausted", provider: "photon", results: [] },
      }),
    }),
  );
  await search("Nirgends");
  await fireEvent.press(await screen.findByText("Search more widely"));
  expect(
    await screen.findByText(/The wider search is not available right now\./),
  ).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Enter it by hand"));
  expect(screen.getByLabelText("Name of the restaurant")).toHaveProp("value", "Nirgends");
});

test("a plan with no room says why instead of suggesting", async () => {
  await openScreen(
    server({
      "POST /v1/itineraries/{itinerary_id}/restaurant-suggestions": () => ({
        ...SUGGESTIONS,
        suggestions: [],
        issues: [
          {
            code: "NO_SLOT_FITS",
            text: "No day of this plan has room for Zur Alten Post inside a meal window and the day's hours without leaving a visit out.",
          },
        ],
      }),
    }),
  );
  await search("alte");
  await fireEvent.press(screen.getByLabelText(/Zur Alten Post, Austrian/));
  await fireEvent.press(screen.getByTestId("find-slots"));
  expect(
    await screen.findByText(/No day of this plan has room for Zur Alten Post/),
  ).toBeOnTheScreen();
  expect(screen.queryByTestId("preview-slot")).toBeNull();
});

test("a restaurant that cannot be placed says which constraints conflict", async () => {
  await openScreen(
    server({
      "POST /v1/itineraries/{itinerary_id}/restaurant-suggestions": () => ({
        status: 422,
        body: {
          detail: "…",
          code: "recalculation_impossible",
          issues: [
            { code: "ALREADY_IN_PLAN", text: "Zur Alten Post is already in this plan, on day 1." },
          ],
        },
      }),
    }),
  );
  await search("alte");
  await fireEvent.press(screen.getByLabelText(/Zur Alten Post, Austrian/));
  await fireEvent.press(screen.getByTestId("find-slots"));
  expect(await screen.findByText(/This change does not fit the plan/)).toBeOnTheScreen();
  expect(screen.getByText(/Zur Alten Post is already in this plan, on day 1\./)).toBeOnTheScreen();
});
