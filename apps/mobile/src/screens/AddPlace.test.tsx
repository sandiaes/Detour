import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeChangeSet,
  makeItinerary,
  makePlaceSuggestions,
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
    "GET /v1/places/search": (c: { params: Record<string, unknown> }) => ({
      query: "Prat",
      results: [SIGHT],
      external: { state: "not_requested", provider: null, results: [] },
    }),
    "POST /v1/itineraries/{itinerary_id}/place-suggestions": () => makePlaceSuggestions(),
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

/** Ask for the best days, keep the best one and preview it. */
async function previewBest() {
  await fireEvent.press(screen.getByTestId("find-days"));
  await screen.findByTestId("place-suggestions");
  await fireEvent.press(screen.getByTestId("preview-change"));
}

async function search(text: string) {
  await fireEvent.changeText(screen.getByLabelText("Sight or town"), text);
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
  await previewBest();

  const asked = client.calls.find((c) => c.path.endsWith("/place-suggestions"));
  expect(asked?.body).toEqual({ place_id: SIGHT.id });
  const preview = client.calls.find((c) => c.path.endsWith("/change-sets"));
  expect(preview?.body).toEqual({ action: "add_place", place_id: SIGHT.id, day: 1 });
  expect(await screen.findByText("Add Prater?")).toBeOnTheScreen();
  expect(screen.getByText("Nothing changes until you accept.")).toBeOnTheScreen();
  expect(
    screen.getByText(
      "Days 1, 2 change · 1 item left out · 1 visit moved · +18 min travel in total.",
    ),
  ).toBeOnTheScreen();
  // What is dropped is shown with a warning, never silently.
  expect(screen.getByText("Left out of the plan")).toBeOnTheScreen();
  expect(screen.getByText("Day 1, 14:03: St. Stephen's Cathedral")).toBeOnTheScreen();
  expect(screen.getByText("Day 1, 15:10: Prater (your addition)")).toBeOnTheScreen();
  expect(screen.getByText("Belvedere: day 1 11:21 → day 2 10:05")).toBeOnTheScreen();
  expect(screen.getByText("Day 1: Gasthaus Zum Test 13:01 → 12:30")).toBeOnTheScreen();
  expect(
    screen.getByText("Day 1: drive Schönbrunn Palace → Prater, about 22 min"),
  ).toBeOnTheScreen();
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(0);

  await fireEvent.press(screen.getByTestId("accept-change"));
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(1);
  // Back on the plan, which shows the new version without another request.
  expect(await screen.findByText(/^Essentials plan/)).toBeOnTheScreen();
  // The list no longer marks a stop the user added (owner, 2026-11-15); its details still do.
  expect(screen.queryByText("Added by you")).toBeNull();
  expect(client.count("GET /v1/itineraries/{itinerary_id}")).toBe(1);
});

test("discarding returns to the plan unchanged", async () => {
  const client = await openPlan();
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await previewBest();
  await fireEvent.press(await screen.findByTestId("discard-change"));
  expect(client.count("POST /v1/change-sets/{change_set_id}/discard")).toBe(1);
  expect(client.count("POST /v1/change-sets/{change_set_id}/apply")).toBe(0);
  expect(await screen.findByText(/^Essentials plan/)).toBeOnTheScreen();
  expect(screen.queryByText("Added by you")).toBeNull();
});

test("drop a pin, name it and choose how long to stay", async () => {
  const client = await openPlan();
  await fireEvent.press(screen.getByRole("tab", { name: "Pin on map" }));
  expect(screen.queryByTestId("find-days")).toBeNull();
  await act(async () => {
    maplibre.map?.onPress({ nativeEvent: { lngLat: [16.4, 48.21] } });
  });
  expect(screen.getByText("Pin at 48.21000, 16.40000")).toBeOnTheScreen();
  // A pin needs a name before the days can be found.
  expect(screen.getByTestId("find-days")).toBeDisabled();
  await fireEvent.changeText(screen.getByLabelText("Name of the place"), "Friend's flat");
  await fireEvent.changeText(screen.getByTestId("stay-length"), "1h30");
  await previewBest();
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
    day: 1,
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
  expect(screen.getByTestId("stay-length-default")).toBeSelected();
  expect(screen.getByTestId("stay-length")).toHaveProp("value", "120");
  await previewBest();
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
  await previewBest();
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
  await previewBest();
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
  await previewBest();
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
  // Lock and Remove are on a stop's details.
  await fireEvent.press(await screen.findByTestId("details-i1"));
  await fireEvent.press(await screen.findByLabelText("Lock Schönbrunn Palace"));
  expect(client.calls.find((c) => c.method === "PATCH")?.body).toEqual({ locked: true });
  expect(await screen.findByText("Locked")).toBeOnTheScreen();
  // A locked visit is never removed: unlock it first.
  expect(screen.getByLabelText("Remove Schönbrunn Palace")).toBeDisabled();
  expect(screen.getByLabelText("Unlock Schönbrunn Palace")).toBeOnTheScreen();

  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  await fireEvent.press(await screen.findByTestId("details-i2"));
  await fireEvent.press(await screen.findByLabelText("Remove Belvedere"));
  const preview = client.calls.find((c) => c.path.endsWith("/change-sets"));
  expect(preview?.body).toEqual({ action: "remove_place", item_id: "i2" });
  expect(await screen.findByText("Remove Belvedere?")).toBeOnTheScreen();
});

// -- step 4 of the redesign (ADR 021): suggested days ------------------------------------------

test("up to three suggested days show the time, travel and what else changes", async () => {
  const client = await openPlan();
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("find-days"));
  expect(
    await screen.findByRole("header", { name: "The 2 best days for Prater" }),
  ).toBeOnTheScreen();
  // The best day: its place in the day, the travel it adds, the item that gets a new time.
  expect(screen.getByText("Day 1 · 15:10–17:10")).toBeOnTheScreen();
  expect(screen.getAllByText("Best")).toHaveLength(1);
  expect(
    screen.getByText("Between St. Stephen's Cathedral and Café Ohne Angabe"),
  ).toBeOnTheScreen();
  expect(screen.getByText("+12 min travel (estimated)")).toBeOnTheScreen();
  expect(screen.getByText("Café Ohne Angabe: 18:30 → 19:00")).toBeOnTheScreen();
  expect(screen.getByText("Adds the least travel of the days that can take it.")).toBeOnTheScreen();
  // The alternative leaves a visit out, and says so first, as a warning.
  expect(screen.getByText("Day 2 · 10:05–12:05")).toBeOnTheScreen();
  expect(screen.getByText("Leaves out Kunsthaus (day 2)")).toBeOnTheScreen();
  expect(screen.getByText("Belvedere moves from day 1 to day 2")).toBeOnTheScreen();
  expect(screen.getByText("+35 min travel (routed)")).toBeOnTheScreen();
  // Asking stores nothing.
  expect(client.count("POST /v1/itineraries/{itinerary_id}/change-sets")).toBe(0);
  // The best is chosen already; choose the other and preview it.
  const best = screen.getByTestId("suggestion-day-1");
  expect(best.props.accessibilityState).toEqual({ selected: true });
  expect(best.props.accessibilityLabel).toMatch(/^Best: Day 1 · 15:10–17:10\. Between /);
  await fireEvent.press(screen.getByTestId("suggestion-day-2"));
  expect(screen.getByTestId("suggestion-day-2").props.accessibilityState).toEqual({
    selected: true,
  });
  await fireEvent.press(screen.getByTestId("preview-change"));
  expect(client.calls.find((c) => c.path.endsWith("/change-sets"))?.body).toEqual({
    action: "add_place",
    place_id: SIGHT.id,
    day: 2,
  });
  expect(await screen.findByText("Add Prater?")).toBeOnTheScreen();
});

test("when no day can take the place, the reasons are shown and nothing can be previewed", async () => {
  await openPlan(
    server({
      "POST /v1/itineraries/{itinerary_id}/place-suggestions": () =>
        makePlaceSuggestions({
          suggestions: [],
          issues: [
            {
              code: "DAY_TOO_SHORT_FOR_ADDITION",
              text: "Day 1: Prater (600 min) does not fit with the day's meals.",
            },
          ],
        }),
    }),
  );
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("find-days"));
  expect(await screen.findByText(/does not fit with the day's meals/)).toBeOnTheScreen();
  expect(screen.getByText(/No day fits/)).toBeOnTheScreen();
  expect(screen.queryByTestId("preview-change")).toBeNull();
});

test("a custom place by address: found through the server, renamed, then placed", async () => {
  const client = await openPlan(
    server({
      "GET /v1/places/search": () => ({
        query: "Hauptplatz 1",
        results: [],
        external: {
          state: "ok",
          provider: "photon",
          results: [
            {
              provider: "photon",
              ref: "N77",
              name: "Hauptplatz 1",
              lat: 47.07,
              lon: 15.44,
              street: "Hauptplatz",
              housenumber: "1",
              postcode: "8010",
              city: "Graz",
              country: "Austria",
              licence: "ODbL",
            },
          ],
        },
      }),
    }),
  );
  await fireEvent.press(screen.getByRole("tab", { name: "Address" }));
  await fireEvent.changeText(screen.getByLabelText("Street address"), "Hauptplatz 1");
  await fireEvent.press(screen.getByTestId("find-address"));
  expect(client.calls.find((c) => c.path === "/v1/places/search")?.params).toMatchObject({
    q: "Hauptplatz 1",
    include_external: true,
  });
  await fireEvent.press(
    await screen.findByLabelText("Hauptplatz 1, Hauptplatz 1, 8010 Graz, Austria"),
  );
  // The name starts as the search result's, and can be changed.
  expect(screen.getByLabelText("Name of the place").props.value).toBe("Hauptplatz 1");
  await fireEvent.changeText(screen.getByLabelText("Name of the place"), "Town hall square");
  await previewBest();
  expect(client.calls.find((c) => c.path === "/v1/user-places")?.body).toEqual({
    kind: "location",
    name: "Town hall square",
    lat: 47.07,
    lon: 15.44,
    source: "search_result",
    search_provider: "photon",
    search_ref: "N77",
  });
});

test("the add-place search asks for sights only: restaurants have their own flow", async () => {
  const kinds: unknown[] = [];
  await openPlan(
    server({
      "GET /v1/places/search": (c: { params: Record<string, unknown> }) => {
        kinds.push(c.params.kind);
        return {
          query: "Sch",
          results: [SIGHT],
          external: { state: "not_requested", provider: null, results: [] },
        };
      },
    }),
  );
  await search("Sch");
  expect(await screen.findByText("Sights")).toBeOnTheScreen();
  expect(kinds).toEqual(["attraction"]);
  expect(screen.queryByText("Places to eat")).toBeNull();
});

test("asking again after changing the length does not save the pin twice", async () => {
  const client = await openPlan();
  await fireEvent.press(screen.getByRole("tab", { name: "Pin on map" }));
  await act(async () => {
    maplibre.map?.onPress({ nativeEvent: { lngLat: [16.4, 48.21] } });
  });
  await fireEvent.changeText(screen.getByLabelText("Name of the place"), "Friend's flat");
  await fireEvent.press(screen.getByTestId("find-days"));
  await screen.findByTestId("place-suggestions");
  await fireEvent.changeText(screen.getByTestId("stay-length"), "2h");
  // A new length asks again, with the same saved place.
  expect(screen.queryByTestId("place-suggestions")).toBeNull();
  await fireEvent.press(screen.getByTestId("find-days"));
  await screen.findByTestId("place-suggestions");
  expect(client.count("POST /v1/user-places")).toBe(1);
  const asked = client.calls.filter((c) => c.path.endsWith("/place-suggestions"));
  expect(asked.map((c) => c.body)).toEqual([
    { user_place_id: "00000000-0000-4000-8000-00000000cc01", duration_minutes: 60 },
    { user_place_id: "00000000-0000-4000-8000-00000000cc01", duration_minutes: 120 },
  ]);
});

const ITEM_PATH = "POST /v1/itineraries/{itinerary_id}/days/{day_index}/items";

test("choose the day and the time directly, without a proposal", async () => {
  const client = await openPlan(server({ [ITEM_PATH]: () => ({ id: "new" }) }));
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("how-choose"));
  await fireEvent.press(screen.getByTestId("slot-day"));
  await fireEvent.press(screen.getByTestId("slot-day-2"));
  await fireEvent.changeText(screen.getByTestId("slot-time"), "9:30");
  await fireEvent.press(screen.getByTestId("add-at-time"));

  expect(client.count("POST /v1/itineraries/{itinerary_id}/place-suggestions")).toBe(0);
  const added = client.calls.find((c) => c.path.endsWith("/days/{day_index}/items"));
  expect(added?.params).toMatchObject({ day_index: 2 });
  expect(added?.body).toMatchObject({
    type: "visit",
    place_id: SIGHT.id,
    start_time: "09:30",
    // A sight left on its usual length is sent without one: the server has it.
    duration_minutes: null,
  });
});

test("Choose day and time starts on the open day, at its first free time", async () => {
  const client = server({ [ITEM_PATH]: () => ({ id: "new" }) });
  await render(
    <Harness client={client} initial={{ ...planRoute, day: 2 }}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByTestId("add-place"));
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  await fireEvent.press(screen.getByTestId("how-choose"));
  expect(screen.getByTestId("slot-day")).toHaveTextContent(/Day 2/);
  // Nothing was typed, so the time is the day's first free time, not a fixed hour.
  const suggested = screen.getByTestId("slot-time").props.value as string;
  expect(suggested).toMatch(/^\d\d:\d\d$/);
  await fireEvent.press(screen.getByTestId("add-at-time"));
  const added = client.calls.find((c) => c.path.endsWith("/days/{day_index}/items"));
  expect(added?.params).toMatchObject({ day_index: 2 });
  expect(added?.body).toMatchObject({ start_time: suggested });
});

test("an empty trip has no suggestion button: the day and time are chosen", async () => {
  const empty = { ...makeItinerary("essentials"), profile: "manual" } as never;
  const client = await openPlan(
    server({ "GET /v1/itineraries/{itinerary_id}": () => empty, [ITEM_PATH]: () => ({ id: "n" }) }),
  );
  await search("Prat");
  await fireEvent.press(await screen.findByLabelText(/Prater, theme park/));
  expect(screen.queryByTestId("find-days")).toBeNull();
  expect(screen.getByTestId("add-at-time")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("add-at-time"));
  expect(client.count(ITEM_PATH)).toBe(1);
  expect(client.count("POST /v1/itineraries/{itinerary_id}/place-suggestions")).toBe(0);
});
