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

test("days list items with times, durations and what the duration is", async () => {
  await openDays();
  expect(await screen.findByText("Day 1 · Sat 1 May")).toBeOnTheScreen();
  expect(
    screen.getByText("3 visits · 2 meals · 4 h 30 min at the sights · 37 min travelling"),
  ).toBeOnTheScreen();
  expect(screen.getByText("Schönbrunn Palace")).toBeOnTheScreen();
  expect(screen.getByText("2 h · typical visit length")).toBeOnTheScreen();
  expect(screen.getByText("1 h 30 min · set by you")).toBeOnTheScreen();
  expect(screen.getByText("A well-known sight.")).toBeOnTheScreen();
  expect(screen.getByText("Close to the previous stop.")).toBeOnTheScreen();
  expect(screen.getByText("Day 2 · Sun 2 May")).toBeOnTheScreen();
});

test("meals show the meal, the venue type and the cuisine from the open data", async () => {
  await openDays();
  expect(await screen.findByText("Gasthaus Zum Test")).toBeOnTheScreen();
  expect(screen.getByText("Lunch · Restaurant")).toBeOnTheScreen();
  expect(screen.getByText("Regional, coffee shop")).toBeOnTheScreen();
  expect(screen.getByText("1 h · typical meal length")).toBeOnTheScreen();
  expect(screen.getByText("Lunch, planned between 12:00 and 14:30.")).toBeOnTheScreen();
  // Unknown cuisine is said plainly, never guessed; no price or rating is shown.
  expect(screen.getByText("Dinner · Restaurant")).toBeOnTheScreen();
  expect(screen.getByText("Cuisine not specified")).toBeOnTheScreen();
  expect(screen.queryByText(/€|EUR|price|rating/i)).toBeNull();
  expect(
    screen.getByLabelText(
      "Stop 3. Lunch · Restaurant. Gasthaus Zum Test. Regional, coffee shop. 13:01 to 14:01. " +
        "1 h, typical meal length. Why: Lunch, planned between 12:00 and 14:30.",
    ),
  ).toBeOnTheScreen();
});

test("an area plan names each day's base city and the drive between them", async () => {
  await openDays();
  expect(await screen.findByText("Based in Vienna")).toBeOnTheScreen();
  expect(screen.getByText("Based in Graz")).toBeOnTheScreen();
  expect(screen.getByText("Drive from Vienna · 2 h 20 min · 191 km")).toBeOnTheScreen();
  expect(
    screen.getByLabelText(
      "Day 2 · Sun 2 May. Based in Graz. 2 visits · 3 h at the sights · 2 h 25 min travelling. " +
        "Starts with: Drive from Vienna · 2 h 20 min · 191 km, estimated, a straight-line " +
        "estimate and not a measured route.",
    ),
  ).toBeOnTheScreen();
});

test("every transfer says its mode, time, distance and whether it is routed or estimated", async () => {
  await openDays();
  await screen.findByText("Schönbrunn Palace");
  expect(screen.getByText("Walk · 21 min · 1.5 km")).toBeOnTheScreen();
  expect(screen.getByText("Drive · 10 min · 4.2 km")).toBeOnTheScreen();
  expect(screen.getAllByText("Estimated").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Routed").length).toBeGreaterThan(0);
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
      "Stop 1. Schönbrunn Palace. 09:00 to 11:00. 2 h, typical visit length. Why: A well-known sight. Close to the previous stop.",
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

test("the list is virtualised: a 14-day plan renders only what is near the screen", async () => {
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
  expect(screen.queryByText("Place 1-40")).toBeNull();
  expect(screen.queryByText("Place 14-40")).toBeNull();
  expect(screen.queryAllByText(/^Place \d+-\d+$/).length).toBeLessThan(40);
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
  await fireEvent.press(await screen.findByText("Vienna, 2 days"));
  expect(await screen.findByText("Not planned yet")).toBeOnTheScreen();
  await act(async () => {
    expect(back.press()).toBe(true);
  });
  expect(await screen.findByRole("header", { name: "Trips" })).toBeOnTheScreen();
  // On the first screen Android is left to close the app.
  expect(back.press()).toBe(false);
});

test("switching to the map keeps the same plan and shows a button per day", async () => {
  await openDays();
  await fireEvent.press(await screen.findByRole("button", { name: "Show the map" }));
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Show day 2 on the map" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Show the day list" }));
  expect(await screen.findByText("Schönbrunn Palace")).toBeOnTheScreen();
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
