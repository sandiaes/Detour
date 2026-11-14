import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { captureBackButton } from "../testing/backButton";
import { createMemoryStore } from "../cache/store";
import { createFakeClient, offline } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

const route = (view: "days" | "map" = "days", day = 1) =>
  ({ name: "itinerary", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, view, day }) as const;

function server(over: Record<string, (c: never) => unknown> = {}) {
  let status: "proposed" | "selected" = "proposed";
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/trips/{trip_id}/itineraries": () => [],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status }),
    "PATCH /v1/trips/{trip_id}": () => {
      status = "selected";
      return makeTrip({ selected_itinerary_id: ESSENTIALS_ID });
    },
    ...over,
  } as never);
}

async function openDays(client = server(), cache = createMemoryStore()) {
  await render(
    <Harness client={client} cache={cache} initial={route()}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("the list shows one day at a time, with times, kinds and durations", async () => {
  await openDays();
  expect(await screen.findByRole("tab", { name: "Day 1, Sat 1 May" })).toBeOnTheScreen();
  // No "Day 1 · Sat 1 May · 3 visits…" title above the stops: the tab names the day.
  expect(screen.queryByText(/visits · .* at the sights/)).toBeNull();
  expect(screen.getByText("Schönbrunn Palace")).toBeOnTheScreen();
  expect(screen.getAllByText("Attraction · 2 h").length).toBeGreaterThan(0);
  // Day 2 is behind its tab in the day selector.
  expect(screen.queryByText("Hofburg")).toBeNull();
  await fireEvent.press(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }));
  expect(await screen.findByText("Hofburg")).toBeOnTheScreen();
  expect(screen.queryByText("Schönbrunn Palace")).toBeNull();
});

test("choosing a stop only selects it: nothing opens under it", async () => {
  await openDays();
  await fireEvent.press(await screen.findByTestId("stop-i1"));
  expect(screen.getByTestId("stop-i1").props.accessibilityState).toMatchObject({ selected: true });
  expect(screen.queryByText("A well-known sight.")).toBeNull();
  expect(screen.queryByText("2 h · typical visit length")).toBeNull();
  expect(screen.queryByLabelText("Lock Schönbrunn Palace")).toBeNull();
  await fireEvent.press(screen.getByTestId("stop-i2"));
  expect(screen.getByTestId("stop-i2").props.accessibilityState).toMatchObject({ selected: true });
  expect(screen.getByTestId("stop-i1").props.accessibilityState).toMatchObject({ selected: false });
});

test("meals show the meal, the venue type and the cuisine from the open data", async () => {
  await openDays();
  expect(await screen.findByText("Gasthaus Zum Test")).toBeOnTheScreen();
  expect(screen.getByText("Lunch · Restaurant · 1 h")).toBeOnTheScreen();
  expect(screen.getByText("Regional, coffee shop")).toBeOnTheScreen();
  // Unknown cuisine is said plainly, never guessed; no price or rating is shown.
  expect(screen.getByText("Dinner · Restaurant · 1 h 30 min")).toBeOnTheScreen();
  expect(screen.getByText("Cuisine not specified")).toBeOnTheScreen();
  expect(screen.queryByText(/€|EUR|price|rating/i)).toBeNull();
  expect(
    screen.getByLabelText(
      "Stop 3. Restaurant. Lunch. Gasthaus Zum Test. Regional, coffee shop. 13:01 to 14:01. " +
        "1 h, typical meal length. Why: Lunch, planned between 13:00 and 15:00.",
    ),
  ).toBeOnTheScreen();
});

test("an area plan names each day's base city and starts a new base with the journey", async () => {
  await openDays();
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }));
  expect(await screen.findByText("Graz")).toBeOnTheScreen();
  expect(screen.getByText("To Graz")).toBeOnTheScreen();
  expect(screen.getByText("Drive from Vienna · 2 h 20 min · 191 km")).toBeOnTheScreen();
  expect(screen.getByLabelText("Day 2 · Sun 2 May. Based in Graz.")).toBeOnTheScreen();
  expect(
    screen.getByRole("button", {
      name:
        "Transport. Drive from Vienna · 2 h 20 min · 191 km, estimated, a straight-line " +
        "estimate and not a measured route. Arrives in Graz.",
    }),
  ).toBeOnTheScreen();
});

test("every transfer says its mode, time, distance and whether it is routed or estimated", async () => {
  await openDays();
  await screen.findByText("Schönbrunn Palace");
  expect(screen.getByText("Walk 21 min 1.5 km")).toBeOnTheScreen();
  expect(screen.getByText("Drive 10 min 4.2 km")).toBeOnTheScreen();
  // The words Routed and Estimated are gone from the list; the spoken label keeps them.
  expect(screen.queryByText("Estimated")).toBeNull();
  expect(screen.queryByText("Routed")).toBeNull();
  // A screen reader hears the same, in a sentence, with what "estimated" means.
  expect(
    screen.getByLabelText(
      "Walk to Belvedere, 21 min, 1.5 km, estimated, a straight-line estimate and not a measured route.",
    ),
  ).toBeOnTheScreen();
  expect(
    screen.getByLabelText("Drive to Gasthaus Zum Test, 10 min, 4.2 km, routed."),
  ).toBeOnTheScreen();
});

test("an item reads as one sentence to a screen reader", async () => {
  await openDays();
  await screen.findByText("Schönbrunn Palace");
  expect(
    screen.getByLabelText(
      "Stop 1. Attraction. Schönbrunn Palace. 09:00 to 11:00. 2 h, typical visit length. Why: A well-known sight. Close to the previous stop.",
    ),
  ).toBeOnTheScreen();
});

test("the estimated transfers are explained once, from the plan's own numbers", async () => {
  await openDays();
  expect(await screen.findByText(/2 transfers of 3 are estimated/)).toBeOnTheScreen();
});

test("plan notes sit behind one control; estimated transfers are explained once, not twice", async () => {
  await openDays(
    server({
      "GET /v1/itineraries/{itinerary_id}": () =>
        makeItinerary("essentials", {
          notes: [
            { code: "ESTIMATED_TRANSFERS", text: "29 of 29 transfers are estimated." },
            { code: "NO_OPENING_HOURS", text: "Opening hours are not checked." },
          ],
        }),
    }),
  );
  await screen.findByText("Schönbrunn Palace");
  expect(screen.queryByText("29 of 29 transfers are estimated.")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "About these plans, 1 notes" }));
  expect(screen.getByText(/Opening hours are not checked/)).toBeOnTheScreen();
});

test("a long plan renders one day at a time: a 14-day plan shows 40 stops, not 560", async () => {
  const big = makeItinerary("essentials");
  big.days = Array.from({ length: 14 }, (_, d) => ({
    id: `day-${d}`,
    day_index: d + 1,
    date: null,
    base_city_id: null,
    items: Array.from({ length: 40 }, (_, i) => ({
      ...big.days[0]!.items[0]!,
      id: `d${d}i${i}`,
      day_id: `day-${d}`,
      position: i + 1,
      display_name: `Place ${d + 1}-${i + 1}`,
      transfer: null,
    })),
  }));
  await openDays(server({ "GET /v1/itineraries/{itinerary_id}": () => big }));
  expect(await screen.findByText("Place 1-1")).toBeOnTheScreen();
  expect(screen.getByText("Place 1-40")).toBeOnTheScreen();
  expect(screen.queryByText("Place 2-1")).toBeNull();
  expect(screen.queryAllByText(/^Place \d+-\d+$/)).toHaveLength(40);
});

test("Select chooses this plan from the day list too", async () => {
  const client = await openDays();
  await fireEvent.press(await screen.findByRole("button", { name: "Select the Essentials plan" }));
  expect(await screen.findByText("✓ Selected")).toBeOnTheScreen();
  expect(client.calls.find((c) => c.method === "PATCH")?.body).toEqual({
    selected_itinerary_id: ESSENTIALS_ID,
  });
});

test("a plan saved on the device opens offline", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makeTrip()]);
  await cache.set(`itinerary:${ESSENTIALS_ID}`, makeItinerary("essentials"));
  const client = createFakeClient({
    "GET /v1/trips": offline,
    "GET /v1/itineraries/{itinerary_id}": offline,
  });
  await render(
    <Harness client={client} cache={cache} initial={route()}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Schönbrunn Palace")).toBeOnTheScreen();
  expect(await screen.findByText(/Showing this plan saved/)).toBeOnTheScreen();
});

test("a plan that was never opened cannot be read offline, and the screen says so", async () => {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/itineraries/{itinerary_id}": offline,
  });
  await render(
    <Harness client={client} initial={route()}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("You are offline")).toBeOnTheScreen();
  expect(screen.getByText(/not saved on the device yet/)).toBeOnTheScreen();
});

test("the Android back button leaves the plan for the screen before it", async () => {
  const back = captureBackButton();
  await render(
    <Harness client={server()} initial={{ name: "trips" }}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByText("Vienna"));
  expect(await screen.findByRole("header", { name: "Choose a plan" })).toBeOnTheScreen();
  await act(async () => {
    expect(back.press()).toBe(true);
  });
  expect(await screen.findByRole("header", { name: "Detour" })).toBeOnTheScreen();
  // On the first screen Android is left to close the app.
  expect(back.press()).toBe(false);
});

test("switching to the map keeps the same plan and day, with the day's list under it", async () => {
  await openDays();
  await fireEvent.press(await screen.findByRole("tab", { name: "Day 2, Sun 2 May" }));
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the map" }));
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  expect(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }).props.accessibilityState).toEqual({
    selected: true,
  });
  expect(screen.getByLabelText("Stop 1, Attraction: Hofburg")).toBeOnTheScreen();
  expect(screen.getByText("Hofburg")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("tab", { name: "Show the day list" }));
  expect(await screen.findByText("Hofburg")).toBeOnTheScreen();
  expect(screen.queryByTestId("map")).toBeNull();
});

test("a marker and its stop in the list highlight each other", async () => {
  await render(
    <Harness client={server()} initial={route("map")}>
      <AppContent />
    </Harness>,
  );
  await screen.findByTestId("map");
  // The map: tapping a marker selects the stop in the list.
  await fireEvent.press(screen.getByTestId("marker-i3"));
  expect(screen.getByTestId("stop-i3").props.accessibilityState).toMatchObject({ selected: true });
  expect(
    screen.getByLabelText("Stop 4, Attraction: St. Stephen's Cathedral").props.accessibilityState,
  ).toEqual({ selected: true });
  // The list: choosing a stop selects its marker.
  await fireEvent.press(screen.getByTestId("stop-i1"));
  expect(
    screen.getByLabelText("Stop 1, Attraction: Schönbrunn Palace").props.accessibilityState,
  ).toEqual({ selected: true });
  expect(
    screen.getByLabelText("Stop 4, Attraction: St. Stephen's Cathedral").props.accessibilityState,
  ).toEqual({ selected: false });
});

test("a stop's details open from its row", async () => {
  await openDays();
  await fireEvent.press(await screen.findByRole("button", { name: "Details of Belvedere" }));
  expect(await screen.findByRole("header", { name: "Belvedere" })).toBeOnTheScreen();
});

test("the map needs a connection and says so, offering the list", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makeTrip()]);
  await cache.set(`itinerary:${ESSENTIALS_ID}`, makeItinerary("essentials"));
  await render(
    <Harness state={{ phase: "error", message: "x" }} cache={cache} initial={route("map")}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("The map needs a connection")).toBeOnTheScreen();
});

test("sights and places to eat are told apart in words, not by colour alone", async () => {
  await openDays();
  await screen.findByText("Gasthaus Zum Test");
  expect(screen.getAllByTestId("kind-attraction")).toHaveLength(3);
  expect(screen.getAllByTestId("kind-restaurant")).toHaveLength(2);
  expect(screen.getByText("Lunch · Restaurant · 1 h")).toBeOnTheScreen();
  expect(screen.getAllByText("Attraction · 2 h").length).toBeGreaterThan(0);
});
