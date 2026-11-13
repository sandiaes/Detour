import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { Dimensions, StyleSheet } from "react-native";

import { AppContent } from "./App";
import { createMemoryStore } from "./cache/store";
import { createFakeClient } from "./testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeDestination,
  makeItinerary,
  makeSummary,
  makeTrip,
} from "./testing/fixtures";
import { Harness } from "./testing/harness";

type Host = ReturnType<typeof screen.getByRole>;

function textOf(el: Host): string {
  return within(el)
    .queryAllByText(/./)
    .map((t) => String(t.props.children))
    .join(" ");
}

/** The size a touch lands on: the element's own height plus its hit slop. */
function touchHeight(el: Host): number {
  const style = StyleSheet.flatten(el.props.style) ?? {};
  const own = Math.max(Number(style.minHeight ?? 0), Number(style.height ?? 0));
  const slop = el.props.hitSlop ?? {};
  return own + Number(slop.top ?? 0) + Number(slop.bottom ?? 0);
}

/** Every control on screen has a spoken name and a touch target of at least 48 dp. */
function checkControls() {
  const controls = [
    ...screen.queryAllByRole("button"),
    ...screen.queryAllByRole("link"),
    ...screen.queryAllByRole("tab"),
  ] as Host[];
  expect(controls.length).toBeGreaterThan(0);
  for (const el of controls) {
    const name = el.props.accessibilityLabel || textOf(el);
    expect({ name, empty: name.trim() === "" }).toMatchObject({ empty: false });
    expect({ name, height: touchHeight(el) >= 48 }).toEqual({ name, height: true });
  }
}

function server() {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/trips/{trip_id}/itineraries": () => [makeSummary("essentials"), makeSummary("wider")],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "GET /v1/attributions": () => [],
    "GET /v1/destinations/search": () => ({
      query: "Vie",
      results: [makeDestination(), makeDestination({ ref: "a", name: "Area", kind: "area" })],
      external: { state: "not_requested", results: [] },
    }),
  });
}

async function show(initial: Parameters<typeof Harness>[0]["initial"], ready: string | RegExp) {
  await render(
    <Harness client={server()} cache={createMemoryStore()} initial={initial}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText(ready);
}

// A phone-width window: the two plans are then swiped, not side by side.
beforeEach(() =>
  Dimensions.set({
    window: { width: 360, height: 740, scale: 2, fontScale: 1 },
    screen: { width: 360, height: 740, scale: 2, fontScale: 1 },
  }),
);

test("trips list", async () => {
  await show({ name: "trips" }, "Vienna, 2 days");
  checkControls();
});

test("create trip form with search results", async () => {
  await show({ name: "createTrip" }, "Details");
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  await screen.findByText("Area", {}, { timeout: 3000 });
  checkControls();
});

test("proposals", async () => {
  await show({ name: "trip", tripId: TRIP_ID }, "How they differ");
  checkControls();
});

test("day list", async () => {
  await show(
    { name: "itinerary", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, view: "days", day: 1 },
    "Schönbrunn Palace",
  );
  checkControls();
});

test("map with markers and the attribution links", async () => {
  await show(
    { name: "itinerary", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, view: "map", day: 1 },
    "Tap a numbered stop for details. ",
  );
  expect(screen.getAllByLabelText(/^Stop \d+: /).length).toBe(5);
  checkControls();
});

test("settings", async () => {
  await show({ name: "settings" }, /Status: connected/);
  checkControls();
});

test("nothing is conveyed by colour alone: states carry words or marks", async () => {
  await show({ name: "trip", tripId: TRIP_ID }, "How they differ");
  // Selected, estimated and offline each have a word in the text, checked elsewhere; this guards
  // the shared controls: a selected chip reads "selected" and shows a check mark.
  const chip = screen.getByRole("button", { name: "Show the Essentials plan, 1 of 2" });
  expect(chip.props.accessibilityState).toMatchObject({ selected: true });
  expect(within(chip).getByText("✓ Essentials")).toBeOnTheScreen();
});
