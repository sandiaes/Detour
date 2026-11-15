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

const SAVED = {
  id: "00000000-0000-4000-8000-00000000ac01",
  kind: "restaurant",
  name: "Zur Alten Post",
  lat: 48.22,
  lon: 16.38,
  source: "manual_pin",
  search_provider: null,
  search_ref: null,
  created_at: "2026-11-14T10:00:00Z",
  updated_at: "2026-11-14T10:00:00Z",
};

const SAVED_CAFE = {
  ...SAVED,
  id: "00000000-0000-4000-8000-00000000ac02",
  kind: "cafe",
  name: "Café Stumm",
};

const NOT_EXTERNAL = { state: "not_requested", provider: null, results: [] };

const ITEM_PATH = "POST /v1/itineraries/{itinerary_id}/days/{day_index}/items";

function server(over: Record<string, (c: never) => unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "GET /v1/restaurants/search": () => ({
      query: "alte",
      your_places: [SAVED, SAVED_CAFE],
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
  expect(await screen.findByText("Add a restaurant or café")).toBeOnTheScreen();
  return client;
}

async function search(text: string) {
  await fireEvent.changeText(screen.getByLabelText("Restaurant or café name"), text);
  await act(async () => {
    jest.advanceTimersByTime(RESTAURANT_DEBOUNCE_MS + 10);
  });
}

test("search your saved places, pick one, choose the day and time", async () => {
  const client = await openScreen();
  await search("alte");
  expect(client.calls.find((c) => c.path === "/v1/restaurants/search")?.params).toMatchObject({
    q: "alte",
    lat: 48.2082,
  });
  // Only the kind: nothing Photon cannot give (ADR 026).
  expect(screen.getByLabelText("Zur Alten Post, Restaurant")).toBeOnTheScreen();
  expect(screen.getByLabelText("Café Stumm, Café")).toBeOnTheScreen();
  expect(screen.queryByText(/ruisine/)).toBeNull();

  // No suggestions: the user chooses. The start time is only a first suggestion.
  expect(screen.queryByTestId("find-slots")).toBeNull();
  await fireEvent.press(screen.getByLabelText("Zur Alten Post, Restaurant"));
  expect(screen.getByTestId("slot-time")).toHaveProp("value", "13:00");
  await fireEvent.press(screen.getByTestId("slot-day"));
  await fireEvent.press(screen.getByTestId("slot-day-2"));
  await fireEvent.changeText(screen.getByTestId("slot-time"), "20:30");
  await fireEvent.press(screen.getByTestId("add-at-time"));

  const added = client.calls.find((c) => c.path.endsWith("/days/{day_index}/items"));
  expect(added?.params).toMatchObject({ day_index: 2 });
  expect(added?.body).toMatchObject({
    type: "meal",
    place_id: null,
    user_place_id: SAVED.id,
    start_time: "20:30",
    locked: false,
  });
  expect(added?.body).not.toHaveProperty("meal_type");
  // Nothing is previewed or recalculated.
  expect(client.count("POST /v1/itineraries/{itinerary_id}/change-sets")).toBe(0);
});

test("a restaurant entered by hand is saved as typed, with its kind, and added", async () => {
  const client = await openScreen();
  await fireEvent.press(screen.getByTestId("hand-mode"));
  expect(screen.getByTestId("add-at-time")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Name"), "Mein Lokal");
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
  }); // no cuisines, no meal types: they are not asked for
  expect(client.calls.find((c) => c.path.endsWith("/days/{day_index}/items"))?.body).toMatchObject({
    type: "meal",
    user_place_id: "00000000-0000-4000-8000-00000000cc09",
  });
});

test("a café is chosen as the kind, and tapping the map fills in the coordinates", async () => {
  const client = await openScreen();
  await fireEvent.press(screen.getByTestId("hand-mode"));
  await fireEvent.changeText(screen.getByLabelText("Name"), "Kaffeehaus");
  await fireEvent.press(screen.getByTestId("venue-cafe"));
  expect(screen.getByTestId("venue-cafe")).toBeSelected();
  await act(async () => {
    maplibre.map?.onPress({ nativeEvent: { lngLat: [16.4, 48.21] } });
  });
  expect(screen.getByLabelText("Latitude")).toHaveProp("value", "48.210000");
  // There is no cuisine field and no meal chips.
  expect(screen.queryByLabelText("Cuisine (optional)")).toBeNull();
  expect(screen.queryByLabelText("Dinner")).toBeNull();
  await fireEvent.press(screen.getByTestId("add-at-time"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "cafe",
    name: "Kaffeehaus",
    lat: 48.21,
    lon: 16.4,
    source: "manual_pin",
  });
});

test("nothing saved: a wider search offers restaurants and cafés with their kind", async () => {
  const client = await openScreen(
    server({
      "GET /v1/restaurants/search": (c: { params: Record<string, unknown> }) => ({
        query: "Hütte",
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
                  venue_type: "cafe",
                },
              ],
            }
          : NOT_EXTERNAL,
      }),
    }),
  );
  await search("Hütte");
  expect(await screen.findByText("Nothing you saved matches “Hütte”.")).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Search more widely"));
  await fireEvent.press(await screen.findByLabelText(/Alm Hütte, Café · Hallstatt/));
  // The kind Photon gave is the starting point, and the user can change it.
  expect(screen.getByTestId("venue-cafe")).toBeSelected();
  expect(screen.getByTestId("venue-restaurant")).not.toBeSelected();
  await fireEvent.press(screen.getByTestId("add-at-time"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "cafe",
    name: "Alm Hütte",
    lat: 47.5,
    lon: 13.1,
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
  expect(screen.getByLabelText("Name")).toHaveProp("value", "Nirgends");
});
