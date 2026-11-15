import type { ItineraryVersion } from "@detour/shared";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { canOptimize, canUndoOptimize, optimizeStops, preselected } from "../domain/optimize";
import type { TripDocument } from "../documents/model";
import { createMemoryDocumentStore } from "../documents/store";
import { createFakeClient } from "../testing/fakeClient";
import {
  CHANGE_ID,
  ESSENTIALS_ID,
  TRIP_ID,
  makeChangeSet,
  makeItinerary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";

jest.setTimeout(30_000);

// Optimize a hand-made trip in the app (ADR 029): the sheet, the stops kept in place, the preview
// and the undo. The order itself is the server's work, so the fake server answers.

const doc = (key: string): TripDocument => ({
  id: `doc-${key}`,
  tripId: TRIP_ID,
  title: "Ticket",
  category: "ticket",
  link: { kind: "place", key, name: key, day: 1 },
  fileName: "ticket.pdf",
  mimeType: "application/pdf",
  sizeBytes: 1000,
  uri: "file:///docs/ticket.pdf",
  createdAt: 1,
});

const plan = () => makeItinerary("essentials", { status: "selected", version: 3 });

const version = (over: Partial<ItineraryVersion> = {}): ItineraryVersion =>
  ({
    version: 2,
    replaced_at: "2026-11-15T10:00:00Z",
    change_set_id: CHANGE_ID,
    action: "optimize",
    target_name: "Shorter order",
    restores_version: null,
    ...over,
  }) as ItineraryVersion;

function server(handlers: Record<string, unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": plan,
    "GET /v1/itineraries/{itinerary_id}/versions": () => [],
    "GET /v1/trips/{trip_id}/itineraries": () => [],
    ...handlers,
  } as never);
}

async function show(
  initial: Parameters<typeof Harness>[0]["initial"],
  client = server(),
  documents = createMemoryDocumentStore(),
) {
  await render(
    <Harness client={client} initial={initial} documents={documents}>
      <AppContent />
    </Harness>,
  );
  return client;
}

const sheet = { name: "optimize", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID } as const;

const change = (over: Record<string, unknown> = {}) =>
  makeChangeSet({
    action: "optimize",
    target_name: "Shorter order",
    notes: [
      {
        code: "OPTIMIZED",
        text: "A shorter order: 12 min less travel (40 min before, 28 min after).",
      },
      { code: "OPTIMIZE_NOT_SHORTEST", text: "A shorter order, not necessarily the shortest." },
      {
        code: "OPTIMIZE_NO_HOURS",
        text: "Opening hours are not known; a place may be closed on its new day.",
      },
    ],
    ...over,
  } as never);

test("the stops with a document start selected, a locked one always stays", () => {
  const p = plan();
  p.days[0]!.items[1]!.locked = true; // Belvedere
  const stops = optimizeStops(p.days, [doc("name:Schönbrunn Palace"), doc("name:Belvedere")]);
  expect(stops.map((s) => s.name).slice(0, 3)).toEqual([
    "Schönbrunn Palace",
    "Belvedere",
    "Gasthaus Zum Test",
  ]);
  expect(stops[0]).toMatchObject({ hasDocument: true, locked: false });
  expect(preselected(stops)).toEqual(["i1"]); // the locked stop is kept by the server anyway
});

test("Optimize is offered from three stops with a place, and the undo only right after it", () => {
  const p = plan();
  expect(canOptimize(p.days)).toBe(true);
  expect(canOptimize([{ ...p.days[1]!, items: p.days[1]!.items.slice(0, 2) }])).toBe(false);
  expect(canUndoOptimize([version()], 3)).toBe(true);
  expect(canUndoOptimize([version()], 4)).toBe(false); // the plan changed since
  expect(canUndoOptimize([version({ restores_version: 1 })], 3)).toBe(false); // that was an undo
  expect(canUndoOptimize([version({ action: "add_place" })], 3)).toBe(false);
  expect(canUndoOptimize([], 3)).toBe(false);
  expect(canUndoOptimize(undefined, 3)).toBe(false);
});

test("the sheet sends the scope and the stops kept, then opens the preview", async () => {
  const bodies: unknown[] = [];
  const client = server({
    "POST /v1/itineraries/{itinerary_id}/optimize": ({ body }: { body: unknown }) => {
      bodies.push(body);
      return change();
    },
    "GET /v1/change-sets/{change_set_id}": () => change(),
  });
  await show(sheet, client, createMemoryDocumentStore([doc("name:Belvedere")]));
  await fireEvent.press(await screen.findByTestId("keep-summary"));
  const belvedere = await screen.findByTestId("keep-i2");
  expect(belvedere.props.accessibilityState.checked).toBe(true);
  expect(screen.getByTestId("keep-i1").props.accessibilityState.checked).toBe(false);
  await fireEvent.press(screen.getByTestId("keep-i1"));
  await fireEvent.press(screen.getByTestId("keep-done"));
  await fireEvent.press(screen.getByTestId("scope-across_days"));
  await fireEvent.press(screen.getByTestId("optimize-run"));
  expect(await screen.findByText("A shorter order?")).toBeTruthy();
  expect(bodies).toEqual([{ scope: "across_days", fixed_item_ids: ["i1", "i2"] }]);
  expect(screen.getByText(/not necessarily the shortest/)).toBeTruthy();
  expect(screen.getByText(/Opening hours are not known/)).toBeTruthy();
  expect(screen.getByTestId("accept-change")).toBeTruthy();
});

test("when nothing is shorter the sheet says so and nothing is changed", async () => {
  const client = server({
    "POST /v1/itineraries/{itinerary_id}/optimize": () => ({
      status: 409,
      body: { code: "no_better_order", message: "No shorter order was found for these stops" },
    }),
  });
  await show(sheet, client);
  await fireEvent.press(await screen.findByTestId("optimize-run"));
  expect(await screen.findByText(/already in a short order/)).toBeTruthy();
  expect(screen.getByTestId("optimize-run")).toBeTruthy();
});

test("the trip menu and the itinerary offer Optimize, and the undo after one", async () => {
  const client = server({
    "GET /v1/itineraries/{itinerary_id}/versions": () => [version()],
    "POST /v1/itineraries/{itinerary_id}/optimize/undo": () =>
      change({ target_name: "Undo Optimize", restores_version: 2 }),
    "GET /v1/change-sets/{change_set_id}": () =>
      change({ target_name: "Undo Optimize", restores_version: 2 }),
  });
  await show({ name: "tripOverview", tripId: TRIP_ID, section: "overview" }, client);
  expect(await screen.findByTestId("itinerary-optimize")).toBeTruthy();
  await fireEvent.press((await screen.findAllByTestId("trip-menu"))[0] as never);
  expect(await screen.findByTestId("menu-optimize")).toBeTruthy();
  await fireEvent.press(await screen.findByTestId("menu-undo-optimize"));
  expect(await screen.findByText("Undo Optimize?")).toBeTruthy();
  expect(client.count("POST /v1/itineraries/{itinerary_id}/optimize/undo")).toBe(1);
});

test("a plan with fewer than three stops is not offered Optimize", async () => {
  const small = plan();
  small.days = [{ ...small.days[0]!, items: small.days[0]!.items.slice(0, 2) }];
  await show(
    { name: "tripOverview", tripId: TRIP_ID, section: "overview" },
    server({ "GET /v1/itineraries/{itinerary_id}": () => small }),
  );
  await screen.findAllByTestId("trip-menu");
  expect(screen.queryByTestId("itinerary-optimize")).toBeNull();
});
