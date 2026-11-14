import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeTrip } from "../testing/fixtures";
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

const ITEM_PATH = "POST /v1/itineraries/{itinerary_id}/days/{day_index}/items";

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
    [ITEM_PATH]: () => ({ id: "new-item" }),
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

test("search the map data, pick the restaurant, choose the day and time", async () => {
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

  // No suggestions (ADR 026): the user chooses.
  expect(screen.queryByTestId("find-slots")).toBeNull();
  await fireEvent.press(screen.getByLabelText(/Zur Alten Post, Austrian/));
  await fireEvent.press(screen.getByTestId("slot-day-2"));
  await fireEvent.changeText(screen.getByTestId("slot-time"), "20:30");
  await fireEvent.press(screen.getByTestId("add-at-time"));

  const added = client.calls.find((c) => c.path.endsWith("/days/{day_index}/items"));
  expect(added?.params).toMatchObject({ day_index: 2 });
  expect(added?.body).toMatchObject({
    type: "meal",
    place_id: POST.id,
    start_time: "20:30",
    locked: false,
  });
  // Nothing is previewed or recalculated.
  expect(client.count("POST /v1/itineraries/{itinerary_id}/change-sets")).toBe(0);
});

test("a restaurant entered by hand without a cuisine is saved as typed and added", async () => {
  const client = await openScreen();
  await fireEvent.press(screen.getByTestId("hand-mode"));
  expect(screen.getByTestId("add-at-time")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Name of the restaurant"), "Mein Lokal");
  // Typed coordinates (a decimal comma is accepted); an out-of-range value is refused.
  await fireEvent.changeText(screen.getByLabelText("Latitude"), "91");
  expect(screen.getByText(/A number from −90 to 90/)).toBeOnTheScreen();
  expect(screen.getByTestId("add-at-time")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Latitude"), "48,2101");
  await fireEvent.changeText(screen.getByLabelText("Longitude"), "16.3702");
  await fireEvent.press(screen.getByTestId("add-at-time"));

  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "restaurant",
    name: "Mein Lokal",
    lat: 48.2101,
    lon: 16.3702,
    source: "manual_pin",
  }); // no cuisines, no meal types: unknown, never invented
  expect(client.calls.find((c) => c.path.endsWith("/days/{day_index}/items"))?.body).toMatchObject({
    type: "meal",
    user_place_id: "00000000-0000-4000-8000-00000000cc09",
  });
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
  // The form's meal chips come first; the slot chooser has chips of its own.
  await fireEvent.press(screen.getAllByLabelText("Dinner")[0]!);
  await fireEvent.press(screen.getByTestId("add-at-time"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "restaurant",
    name: "Trattoria",
    lat: 48.21,
    lon: 16.4,
    cuisines: ["italian", "pizza"],
    meal_types: ["dinner"],
    source: "manual_pin",
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
  expect(screen.getAllByLabelText("Lunch")[0]).toBeSelected();
  expect(screen.getAllByLabelText("Dinner")[0]).toBeSelected();
  expect(screen.getAllByLabelText("Breakfast")[0]).not.toBeSelected();
  await fireEvent.press(screen.getByTestId("add-at-time"));
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
