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
import { SEARCH_DEBOUNCE_MS } from "./AddPlaceScreen";

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

const SIGHT = {
  id: "00000000-0000-4000-8000-00000000ab01",
  name: "Prater",
  kind: "attraction",
  category: "theme_park",
  lat: 48.2167,
  lon: 16.3958,
  region_id: "austria",
  city_id: 900101,
  city_name: "Vienna",
  distance_m: 2300,
};

const TOWN = {
  kind: "city",
  ref: "900199",
  name: "Melk",
  country_iso2: "AT",
  country_name: "Austria",
  admin1_name: "Lower Austria",
  population: 5000,
  admin_level: null,
  lat: 48.227,
  lon: 15.331,
  region_id: "austria",
  planning_available: true,
  match: "exact",
};

function updatedPlan() {
  const plan = makeItinerary("essentials", { version: 2 });
  const day = plan.days[0]!;
  day.items = [
    ...day.items,
    {
      ...day.items[0]!,
      id: "added",
      position: day.items.length + 1,
      display_name: "Prater",
      origin: "user",
      reasons: ["ADDED_BY_YOU"],
      reason_texts: ["You added this place: every recalculation keeps it in the plan."],
      transfer: null,
    },
  ];
  return plan;
}

function server(over: Record<string, (c: never) => unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "GET /v1/places/search": () => ({
      query: "Prat",
      results: [SIGHT],
      external: { state: "not_requested", provider: null, results: [] },
    }),
    "GET /v1/destinations/search": () => ({
      query: "Prat",
      results: [],
      external: { state: "not_requested", provider: null, results: [] },
    }),
    "POST /v1/itineraries/{itinerary_id}/change-sets": () => makeChangeSet(),
    "GET /v1/change-sets/{change_set_id}": () => makeChangeSet(),
    "POST /v1/change-sets/{change_set_id}/apply": () => ({
      change_set: makeChangeSet({ status: "applied", result_version: 2 }),
      itinerary: updatedPlan(),
    }),
    "POST /v1/change-sets/{change_set_id}/discard": () => makeChangeSet({ status: "discarded" }),
    "POST /v1/user-places": (c: { body: Record<string, unknown> }) => ({
      id: "00000000-0000-4000-8000-00000000cc01",
      ...c.body,
    }),
    ...over,
  } as never);
}

async function openPlan(client = server()) {
  await render(
    <Harness client={client} initial={planRoute}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByTestId("add-place"));
  expect(await screen.findByText("Add a place")).toBeOnTheScreen();
  return client;
}

async function search(text: string) {
  await fireEvent.changeText(screen.getByLabelText("Sight, town or place"), text);
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10);
  });
}

test("search a sight, preview the change, accept it, and see the new plan", async () => {
  const client = await openPlan();
  await search("Prat");
  const search_ = client.calls.find((c) => c.path === "/v1/places/search");
  expect(search_?.params).toMatchObject({ q: "Prat", kind: "attraction", lat: 48.2082 });
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  // A sight has a typical length unless the user picks one.
  expect(screen.getByLabelText("Typical length")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("preview-change"));

  const preview = client.calls.find((c) => c.path.endsWith("/change-sets"));
  expect(preview?.body).toEqual({ action: "add_place", place_id: SIGHT.id });
  expect(await screen.findByText("Add Prater?")).toBeOnTheScreen();
  expect(screen.getByText("Nothing changes until you accept.")).toBeOnTheScreen();
  expect(
    screen.getByText(
      "Days 1, 2 change · 1 item left out · 1 visit moved · +18 min travel in total.",
    ),
  ).toBeOnTheScreen();
  // What is dropped is shown with a warning, never silently.
  expect(screen.getByText("Left out of the plan")).toBeOnTheScreen();
  expect(screen.getByText("• Day 1, 14:03: St. Stephen's Cathedral")).toBeOnTheScreen();
  expect(screen.getByText("• Day 1, 15:10: Prater (your addition)")).toBeOnTheScreen();
  expect(screen.getByText("• Belvedere: day 1 11:21 → day 2 10:05")).toBeOnTheScreen();
  expect(screen.getByText("• Day 1: Lunch at Gasthaus Zum Test 13:01 → 12:30")).toBeOnTheScreen();
  expect(
    screen.getByText("• Day 1: drive Schönbrunn Palace → Prater, about 22 min"),
  ).toBeOnTheScreen();
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(0);

  await fireEvent.press(screen.getByTestId("accept-change"));
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(1);
  // Back on the plan, which shows the new version without another request.
  expect(await screen.findByText("Essentials plan")).toBeOnTheScreen();
  expect(await screen.findByText("Added by you")).toBeOnTheScreen();
  expect(client.count("GET /v1/itineraries/{itinerary_id}")).toBe(1);
});

test("discarding returns to the plan unchanged", async () => {
  const client = await openPlan();
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("preview-change"));
  await fireEvent.press(await screen.findByTestId("discard-change"));
  expect(client.count("POST /v1/change-sets/{change_set_id}/discard")).toBe(1);
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(0);
  expect(await screen.findByText("Essentials plan")).toBeOnTheScreen();
  expect(screen.queryByText("Added by you")).toBeNull();
});

test("drop a pin, name it and choose how long to stay", async () => {
  const client = await openPlan();
  await fireEvent.press(screen.getByTestId("pin-mode"));
  expect(screen.getByTestId("preview-change")).toBeDisabled();
  await act(async () => {
    maplibre.map?.onPress({ nativeEvent: { lngLat: [16.4, 48.21] } });
  });
  expect(screen.getByText("Pin at 48.21000, 16.40000")).toBeOnTheScreen();
  // A pin needs a name before it can be previewed.
  expect(screen.getByTestId("preview-change")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Name of the place"), "Friend's flat");
  await fireEvent.press(screen.getByLabelText("1 h 30 min"));
  await fireEvent.press(screen.getByTestId("preview-change"));
  const saved = client.calls.find((c) => c.path === "/v1/user-places");
  expect(saved?.body).toEqual({
    kind: "location",
    name: "Friend's flat",
    lat: 48.21,
    lon: 16.4,
    source: "manual_pin",
  });
  const preview = client.calls.find((c) => c.path.endsWith("/change-sets"));
  expect(preview?.body).toEqual({
    action: "add_place",
    user_place_id: "00000000-0000-4000-8000-00000000cc01",
    duration_minutes: 90,
  });
  expect(await screen.findByText("Add Prater?")).toBeOnTheScreen();
});

test("a town is saved as a place from the gazetteer and staying two hours is the default", async () => {
  const client = await openPlan(
    server({
      "GET /v1/places/search": () => ({
        query: "Melk",
        results: [],
        external: { state: "not_requested", provider: null, results: [] },
      }),
      "GET /v1/destinations/search": () => ({
        query: "Melk",
        results: [TOWN],
        external: { state: "not_requested", provider: null, results: [] },
      }),
    }),
  );
  await search("Melk");
  await fireEvent.press(await screen.findByLabelText("Melk, Lower Austria, Austria"));
  expect(screen.getByLabelText("2 h")).toBeSelected();
  await fireEvent.press(screen.getByTestId("preview-change"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "city",
    name: "Melk",
    lat: 48.227,
    lon: 15.331,
    source: "search_result",
    search_provider: "geonames",
    search_ref: "900199",
  });
});

test("when nothing is found locally, a wider search can be asked for", async () => {
  const client = await openPlan(
    server({
      "GET /v1/places/search": (c: { params: Record<string, unknown> }) => ({
        query: "Hütte",
        results: [],
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
                },
              ],
            }
          : { state: "not_requested", provider: null, results: [] },
      }),
    }),
  );
  await search("Hütte");
  expect(
    await screen.findByText("Nothing in the imported data matches “Hütte”."),
  ).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Search more widely"));
  await fireEvent.press(await screen.findByLabelText("Alm Hütte, Hallstatt, Austria"));
  await fireEvent.press(screen.getByTestId("preview-change"));
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toMatchObject({
    source: "search_result",
    search_provider: "photon",
    search_ref: "N42",
  });
});

test("an addition that does not fit says which constraints conflict", async () => {
  const client = await openPlan(
    server({
      "POST /v1/itineraries/{itinerary_id}/change-sets": () => ({
        status: 422,
        body: {
          detail: "…",
          code: "recalculation_impossible",
          issues: [
            {
              code: "DAY_FULL_OF_FIXED_ITEMS",
              text: "Day 1: Prater (240 min) does not fit around the items that cannot move (Belvedere), even with every other visit of the day left out.",
            },
          ],
        },
      }),
    }),
  );
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("preview-change"));
  expect(await screen.findByText(/This change does not fit the plan/)).toBeOnTheScreen();
  expect(screen.getByText(/items that cannot move \(Belvedere\)/)).toBeOnTheScreen();
  expect(screen.getByText("Add a place")).toBeOnTheScreen();
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(0);
});

test("accepting an out-of-date preview says so", async () => {
  await openPlan(
    server({
      "POST /v1/change-sets/{change_set_id}/apply": () => ({
        status: 409,
        body: { detail: "stale", code: "change_set_stale" },
      }),
    }),
  );
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("preview-change"));
  await fireEvent.press(await screen.findByTestId("accept-change"));
  expect(
    await screen.findByText(/The plan changed after this preview. Preview the change again./),
  ).toBeOnTheScreen();
});

test("lock and remove items from the plan", async () => {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "PATCH /v1/items/{item_id}": (c: {
      params: { item_id: string };
      body: { locked: boolean };
    }) => ({
      id: c.params.item_id,
      locked: c.body.locked,
    }),
    "POST /v1/itineraries/{itinerary_id}/change-sets": () =>
      makeChangeSet({ action: "remove_place", target_name: "Belvedere" }),
  } as never);
  await render(
    <Harness client={client} initial={planRoute}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByLabelText("Lock Schönbrunn Palace"));
  expect(client.calls.find((c) => c.method === "PATCH")?.body).toEqual({ locked: true });
  expect(await screen.findByText("Locked")).toBeOnTheScreen();
  // A locked visit is never removed: unlock it first.
  expect(screen.getByLabelText("Remove Schönbrunn Palace")).toBeDisabled();
  expect(screen.getByLabelText("Unlock Schönbrunn Palace")).toBeOnTheScreen();

  await fireEvent.press(screen.getByLabelText("Remove Belvedere"));
  const preview = client.calls.find((c) => c.path.endsWith("/change-sets"));
  expect(preview?.body).toEqual({ action: "remove_place", item_id: "i2" });
  expect(await screen.findByText("Remove Belvedere?")).toBeOnTheScreen();
});
