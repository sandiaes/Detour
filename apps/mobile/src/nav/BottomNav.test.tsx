import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makePastTrip, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { showsBottomNav, tripContext } from "./BottomNav";

function server(trip = makeTrip({ selected_itinerary_id: ESSENTIALS_ID })) {
  return createFakeClient({
    "GET /v1/trips": () => [trip],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/itineraries": () => [],
    "GET /v1/attributions": () => [],
  });
}

async function show(initial: Parameters<typeof Harness>[0]["initial"], client = server()) {
  await render(
    <Harness client={client} initial={initial}>
      <AppContent />
    </Harness>,
  );
}

test("outside a trip, Add starts a new trip", async () => {
  await show({ name: "trips" });
  await screen.findByText("Vienna");
  await fireEvent.press(screen.getByRole("button", { name: "Add a trip" }));
  expect(await screen.findByRole("header", { name: "Create new trip" })).toBeOnTheScreen();
});

test("inside a trip, Add offers a place or restaurant through the adjustment flow", async () => {
  await show({ name: "tripOverview", tripId: TRIP_ID });
  await screen.findByTestId("day-row-1");
  await fireEvent.press(screen.getByRole("button", { name: "Add to this trip" }));
  expect(await screen.findByRole("header", { name: "Add to this trip" })).toBeOnTheScreen();
  // Not built yet: notes say so and cannot be pressed. Transport is built (ADR 032).
  const note = screen.getByRole("button", { name: /^Note\./ });
  expect(note.props.accessibilityState).toMatchObject({ disabled: true });
  expect(note.props.accessibilityLabel).toMatch(/Coming later$/);
  expect(
    screen.getByRole("button", { name: /^Transport\./ }).props.accessibilityState,
  ).toMatchObject({ disabled: false });
  await fireEvent.press(screen.getByRole("button", { name: /^Place\./ }));
  expect(await screen.findByRole("header", { name: /^Add a place/ })).toBeOnTheScreen();
});

test("Add on a trip opens Add transport for the active itinerary (ADR 032)", async () => {
  await show({ name: "tripOverview", tripId: TRIP_ID });
  await screen.findByTestId("day-row-1");
  await fireEvent.press(screen.getByRole("button", { name: "Add to this trip" }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Transport\./ }));
  expect(await screen.findByRole("header", { name: /^Add transport/ })).toBeOnTheScreen();
});

test("Add on a trip opens the restaurant flow for the active itinerary", async () => {
  await show({ name: "tripOverview", tripId: TRIP_ID });
  await screen.findByTestId("day-row-1");
  await fireEvent.press(screen.getByRole("button", { name: "Add to this trip" }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Restaurant\./ }));
  expect(
    await screen.findByRole("header", { name: /^Add a restaurant or café/ }),
  ).toBeOnTheScreen();
});

test("without a chosen plan, places and restaurants wait for a plan", async () => {
  await show({ name: "tripOverview", tripId: TRIP_ID }, server(makeTrip()));
  await screen.findByRole("header", { name: "Choose a plan" });
  await fireEvent.press(screen.getByRole("button", { name: "Add to this trip" }));
  const place = await screen.findByRole("button", { name: /^Place\. Choose a plan first\./ });
  expect(place.props.accessibilityState).toMatchObject({ disabled: true });
  // The backdrop and the close button both close the sheet.
  const close = screen.getAllByRole("button", { name: "Close" });
  expect(close).toHaveLength(2);
  await fireEvent.press(close[1] as (typeof close)[number]);
  expect(screen.queryByRole("header", { name: "Add to this trip" })).toBeNull();
  expect(await screen.findByRole("header", { name: "Choose a plan" })).toBeOnTheScreen();
});

test("a past trip cannot be added to", async () => {
  await show(
    { name: "pastTrip", tripId: TRIP_ID },
    createFakeClient({
      "GET /v1/trips": () => [makePastTrip()],
      "GET /v1/trips/{trip_id}/visits": () => [],
      "GET /v1/trips/{trip_id}/archive": () => ({
        trip_id: TRIP_ID,
        cities: 0,
        attractions: 0,
        skipped: 0,
        size_bytes: 0,
      }),
    }),
  );
  await fireEvent.press(await screen.findByRole("button", { name: "Add to this trip" }));
  expect(
    await screen.findByRole("button", { name: /^Place\. A past trip cannot be changed\./ }),
  ).toBeOnTheScreen();
});

test("Map, Photos and More are root tabs; the unbuilt ones say so", async () => {
  await show({ name: "trips" });
  await screen.findByText("Vienna");
  await fireEvent.press(screen.getByRole("tab", { name: "World map" }));
  expect(await screen.findByRole("header", { name: "Map" })).toBeOnTheScreen();
  expect(screen.getByRole("tab", { name: "World map" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  await fireEvent.press(screen.getByRole("tab", { name: "Photos" }));
  expect(await screen.findByTestId("photos-empty")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  for (const name of [/^Saved places\./, /^Travel preferences\./, /^Archive trip\./]) {
    expect(screen.getByRole("button", { name }).props.accessibilityState).toMatchObject({
      disabled: true,
    });
  }
  // The backup and the import (ADR 028) are built.
  for (const name of [/^Back up all trips\./, /^Import a trip\./]) {
    expect(screen.getByRole("button", { name }).props.accessibilityState).toMatchObject({
      disabled: false,
    });
  }
  await fireEvent.press(screen.getByTestId("more-settings"));
  expect(await screen.findByRole("header", { name: "Settings" })).toBeOnTheScreen();
  // Settings is pushed from More: Back returns there, and the bar marks More.
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: "More" })).toBeOnTheScreen();
});

test("the bar stays on a trip's main screens and leaves forms alone", () => {
  expect(showsBottomNav({ name: "trips" }, 1)).toBe(true);
  expect(showsBottomNav({ name: "tripOverview", tripId: "t" }, 2)).toBe(true);
  expect(
    showsBottomNav({ name: "itinerary", tripId: "t", itineraryId: "i", view: "days", day: 1 }, 3),
  ).toBe(true);
  expect(showsBottomNav({ name: "createTrip" }, 2)).toBe(false);
  expect(showsBottomNav({ name: "addPlace", tripId: "t", itineraryId: "i" }, 3)).toBe(false);
  expect(showsBottomNav({ name: "settings" }, 2)).toBe(false);
  expect(tripContext({ name: "tripOverview", tripId: "t" })).toBe("t");
  expect(tripContext({ name: "trips" })).toBeNull();
});

test("a past trip with a plan cannot be added to either", async () => {
  await show(
    { name: "tripOverview", tripId: TRIP_ID },
    server(makeTrip({ status: "past", selected_itinerary_id: ESSENTIALS_ID })),
  );
  await fireEvent.press(await screen.findByRole("button", { name: "Add to this trip" }));
  for (const name of ["Place", "Restaurant", "Transport"]) {
    const row = await screen.findByRole("button", {
      name: new RegExp(`^${name}\\. A past trip cannot be changed\\.`),
    });
    expect(row.props.accessibilityState).toMatchObject({ disabled: true });
  }
  // A document is not a change to the trip: it stays available.
  expect(screen.getByTestId("add-sheet-document")).toBeOnTheScreen();
});
