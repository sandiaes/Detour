import { fireEvent, render, screen } from "@testing-library/react-native";
import * as ReactNative from "react-native";

import { AppContent } from "../App";
import { createMemoryStore } from "../cache/store";
import { createFakeClient } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  WIDER_ID,
  makeItinerary,
  makeSummary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { SIDE_BY_SIDE_MIN_WIDTH, visiblePlans } from "./TripScreen";

function windowWidth(width: number) {
  ReactNative.Dimensions.set({
    window: { width, height: 740, scale: 2, fontScale: 1 },
    screen: { width, height: 740, scale: 2, fontScale: 1 },
  });
}

beforeEach(() => windowWidth(360));

const open = { name: "trip", tripId: TRIP_ID } as const;

function server(over: Record<string, (c: never) => unknown> = {}) {
  let selected: string | null = null;
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: selected })],
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: selected === ESSENTIALS_ID ? "selected" : "proposed" }),
      makeSummary("wider", { status: selected === WIDER_ID ? "selected" : "proposed" }),
    ],
    "GET /v1/itineraries/{itinerary_id}": ({ params }: { params: Record<string, string> }) =>
      makeItinerary(params.itinerary_id === WIDER_ID ? "wider" : "essentials"),
    "PATCH /v1/trips/{trip_id}": ({ body }: { body: { selected_itinerary_id: string } }) => {
      selected = body.selected_itinerary_id;
      return makeTrip({ selected_itinerary_id: selected });
    },
    ...over,
  } as never);
}

async function openTrip(client = server(), cache = createMemoryStore()) {
  await render(
    <Harness client={client} cache={cache} initial={open}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("two proposals are compared with a structured summary of how they differ", async () => {
  await openTrip();
  expect(await screen.findByText("How they differ")).toBeOnTheScreen();
  expect(screen.getByLabelText("Visits: Essentials 5. Wider 8.")).toBeOnTheScreen();
  expect(
    screen.getByLabelText("Travel time: Essentials 40 min. Wider 1 h 35 min."),
  ).toBeOnTheScreen();
  expect(screen.getByText("• Wider has 3 visits more than Essentials.")).toBeOnTheScreen();
  expect(screen.getByText("• About 40 % of the visits are in both plans.")).toBeOnTheScreen();
  // Both can be reached without swiping: a button per plan.
  expect(
    screen.getByRole("button", { name: "Show the Essentials plan, 1 of 2" }),
  ).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Show the Wider plan, 2 of 2" })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Select the Essentials plan" })).toBeOnTheScreen();
});

test("on a wide screen the two plans sit side by side instead of in a swipe list", async () => {
  windowWidth(SIDE_BY_SIDE_MIN_WIDTH + 80);
  await openTrip();
  await screen.findByText("How they differ");
  expect(screen.getByRole("button", { name: "Select the Essentials plan" })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Select the Wider plan" })).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: /Show the Essentials plan/ })).toBeNull();
});

test("the plans are in a horizontal, snapping list so they can be swiped", async () => {
  await openTrip();
  await screen.findByText("How they differ");
  const pager = screen.getByTestId("plan-pager");
  expect(pager.props.horizontal).toBe(true);
  expect(pager.props.snapToInterval).toBeGreaterThan(0);
});

test("selecting a plan opens the trip's overview on it, and Back from there goes to the trips", async () => {
  const client = await openTrip();
  await fireEvent.press(await screen.findByRole("button", { name: "Select the Essentials plan" }));
  // The chosen plan is now the trip's active itinerary (ADR 021).
  expect(await screen.findByRole("header", { name: "Your itinerary" })).toBeOnTheScreen();
  expect(screen.getByText("Essentials plan")).toBeOnTheScreen();
  const patch = client.calls.find((c) => c.method === "PATCH");
  expect(patch?.body).toEqual({ selected_itinerary_id: ESSENTIALS_ID });
  expect(patch?.params).toMatchObject({ trip_id: TRIP_ID });
  expect(client.count("GET /v1/trips")).toBe(1);
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: "Trips" })).toBeOnTheScreen();
});

test("after new proposals were asked for, the chosen plan is kept apart from the new pair", async () => {
  await openTrip(
    server({
      "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: "old" })],
      "GET /v1/trips/{trip_id}/itineraries": () => [
        makeSummary("essentials", {
          id: "old",
          generation_id: "g0",
          status: "selected",
          created_at: "2026-01-01T00:00:00Z",
        }),
        makeSummary("essentials", { created_at: "2026-02-01T00:00:00Z" }),
        makeSummary("wider", { created_at: "2026-02-01T00:00:00Z" }),
      ],
    }),
  );
  expect(await screen.findByText(/It stays selected, with the places you added/)).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "The Essentials plan is selected" })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Select the Essentials plan" })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Select the Wider plan" })).toBeOnTheScreen();
});

test("a failed selection says so and leaves the choice open", async () => {
  await openTrip(
    server({
      "PATCH /v1/trips/{trip_id}": () => ({ status: 500, body: { detail: "x", code: null } }),
    }),
  );
  await fireEvent.press(await screen.findByRole("button", { name: "Select the Wider plan" }));
  expect(await screen.findByText(/The server had a problem/)).toBeOnTheScreen();
  expect(screen.queryByText("✓ Selected")).toBeNull();
});

test("View days and View map open the plan in that view", async () => {
  await openTrip();
  await fireEvent.press(
    await screen.findByRole("button", { name: "View the days of the Wider plan" }),
  );
  expect(await screen.findByRole("header", { name: "Wider plan" })).toBeOnTheScreen();
  expect(await screen.findByText("Day 1 · Sat 1 May")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText("How they differ")).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole("button", { name: "View the Essentials plan on the map" }),
  );
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
});

test("opening a plan again makes no second request for it", async () => {
  const client = await openTrip();
  await fireEvent.press(
    await screen.findByRole("button", { name: "View the days of the Wider plan" }),
  );
  await screen.findByText("Day 1 · Sat 1 May");
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  await fireEvent.press(
    await screen.findByRole("button", { name: "View the days of the Wider plan" }),
  );
  expect(await screen.findByText("Day 1 · Sat 1 May")).toBeOnTheScreen();
  expect(client.count("GET /v1/itineraries/{itinerary_id}")).toBe(1);
  expect(client.count("GET /v1/trips/{trip_id}/itineraries")).toBe(1);
});

test("the plan notes are one tap away, including that opening hours are not checked", async () => {
  const notes = [
    { code: "PROFILE_ESSENTIALS", text: "Essentials: the highest-ranked sights." },
    { code: "NO_OPENING_HOURS", text: "Opening hours are not checked: a place may be closed." },
  ];
  await openTrip(
    server({
      "GET /v1/trips/{trip_id}/itineraries": () => [
        makeSummary("essentials", { notes }),
        makeSummary("wider", { notes }),
      ],
    }),
  );
  const toggle = await screen.findByRole("button", { name: "About these plans, 1 notes" });
  expect(screen.queryByText(/Opening hours are not checked/)).toBeNull();
  await fireEvent.press(toggle);
  expect(screen.getByText(/Opening hours are not checked/)).toBeOnTheScreen();
  expect(screen.queryByText(/highest-ranked sights/)).toBeNull(); // the card already says it
});

test("a destination that supports one plan shows it with the backend's explanation", async () => {
  await openTrip(
    server({
      "GET /v1/trips/{trip_id}/itineraries": () => [
        makeSummary("essentials", {
          diversity_score: null,
          notes: [
            { code: "SINGLE_PLAN", text: "This destination supports only one distinct plan." },
          ],
        }),
      ],
    }),
  );
  expect(
    await screen.findByText("This destination supports only one distinct plan."),
  ).toBeOnTheScreen();
  expect(screen.queryByText("How they differ")).toBeNull();
});

test("a trip with no plans offers to plan it, and the new plans appear", async () => {
  let planned = false;
  const client = server({
    "GET /v1/trips/{trip_id}/itineraries": () =>
      planned ? [makeSummary("essentials"), makeSummary("wider")] : [],
    "POST /v1/trips/{trip_id}/itineraries/generate": () => {
      planned = true;
      return {
        generation_id: "g",
        distinct: true,
        jaccard_permille: 400,
        max_jaccard_permille: 600,
        notes: [],
        itineraries: [makeItinerary("essentials"), makeItinerary("wider")],
      };
    },
  });
  await openTrip(client);
  await fireEvent.press(await screen.findByRole("button", { name: "Plan this trip" }));
  expect(await screen.findByText("How they differ")).toBeOnTheScreen();
});

test("a trip that is past shows its saved places, not proposals", async () => {
  await openTrip(
    server({
      "GET /v1/trips": () => [makeTrip({ status: "past", archived_at: "2027-06-01T00:00:00Z" })],
      "GET /v1/trips/{trip_id}/visits": () => [],
      "GET /v1/trips/{trip_id}/archive": () => ({
        trip_id: TRIP_ID,
        cities: 0,
        attractions: 0,
        skipped: 0,
        size_bytes: 300,
      }),
    }),
  );
  expect(await screen.findByText("Nothing was kept")).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Plan this trip" })).toBeNull();
});

test("offline, saved plans are shown with a notice", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makeTrip()]);
  await cache.set(`itineraries:${TRIP_ID}`, [makeSummary("essentials"), makeSummary("wider")]);
  await render(
    <Harness state={{ phase: "error", message: "x" }} cache={cache} initial={open}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("How they differ")).toBeOnTheScreen();
  expect(
    screen.getAllByText(/You can read them, but changes need a connection/).length,
  ).toBeGreaterThan(0);
});

test("visiblePlans shows the newest generation, Essentials first, and keeps an older selection", () => {
  const old = makeSummary("wider", {
    id: "old",
    generation_id: "g0",
    status: "selected",
    created_at: "2026-01-01T00:00:00Z",
  });
  const shown = visiblePlans([
    makeSummary("wider", { created_at: "2026-02-01T00:00:00Z" }),
    makeSummary("essentials", { created_at: "2026-02-01T00:00:00Z" }),
    old,
    makeSummary("wider", { id: "gone", status: "superseded" }),
  ]);
  expect(shown.map((p) => p.id)).toEqual([ESSENTIALS_ID, "old", WIDER_ID]);
});
