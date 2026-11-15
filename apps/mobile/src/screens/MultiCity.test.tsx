import type { Day, Trip } from "@detour/shared";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { arrivalText } from "../components/plan/DayPlan";
import { evenSplit, moveStop, stopsProblem, type StopDraft } from "../components/StopList";
import { transportFeature } from "../domain/itinerary";
import { createFakeClient } from "../testing/fakeClient";
import {
  CHANGE_ID,
  ESSENTIALS_ID,
  TRIP_ID,
  makeDestination,
  makeItinerary,
  makeSummary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { madeForEarlierStops } from "./TripScreen";

// Rendering the whole app through two screens takes a few seconds on a slow machine.
jest.setTimeout(30_000);

// Multi-city trips in the app (ADR 024): the stop list, creating a route, editing its cities,
// plans made for earlier cities, and legs whose time is not calculated.

const stop = (cityId: number, name: string, days: number): StopDraft => ({
  cityId,
  name,
  detail: "",
  days,
});

function routeTrip(over: Partial<Trip> = {}): Trip {
  return makeTrip({
    title: "Vienna to Salzburg",
    destination: {
      kind: "route",
      ref: "900101",
      name: "Vienna to Salzburg",
      lat: 48.2,
      lon: 16.37,
    },
    duration_days: 3,
    stops: [
      {
        position: 1,
        city_id: 900101,
        name: "Vienna",
        country_iso2: "AT",
        lat: 48.2,
        lon: 16.37,
        days: 2,
      },
      {
        position: 2,
        city_id: 900102,
        name: "Salzburg",
        country_iso2: "AT",
        lat: 47.8,
        lon: 13.04,
        days: 1,
      },
    ],
    stops_version: 0,
    ...over,
  } as Partial<Trip>);
}

test("days are split evenly, the rest to the first cities", () => {
  expect(evenSplit(5, 2)).toEqual([3, 2]);
  expect(evenSplit(7, 3)).toEqual([3, 2, 2]);
  expect(evenSplit(1, 3)).toEqual([1, 1, 1]); // at least a day each
});

test("the stop rules are checked before anything is sent", () => {
  expect(stopsProblem([stop(1, "A", 1)])).toMatch(/at least two/);
  expect(stopsProblem([stop(1, "A", 1), stop(1, "A", 1)])).toMatch(/same/);
  expect(stopsProblem([stop(1, "A", 20), stop(2, "B", 11)])).toMatch(/30 days/);
  expect(stopsProblem([stop(1, "A", 1), stop(2, "B", 1), stop(1, "A", 1)])).toBeNull();
  expect(moveStop([stop(1, "A", 1), stop(2, "B", 1)], 1, 0).map((s) => s.name)).toEqual(["B", "A"]);
});

test("a leg with no time says so and draws no line", () => {
  const day = {
    arrival: {
      from_base_city_id: 1,
      from_base_city_name: "Tokyo",
      mode: "unknown",
      seconds: null,
      meters: null,
      confidence: "unknown",
    },
  } as unknown as Day;
  expect(arrivalText(day)).toBe(
    "Travel from Tokyo · time not calculated: public transport is not built yet",
  );
  expect(
    transportFeature({
      id: "t",
      dayId: "d",
      name: "Kyoto",
      fromName: "Tokyo",
      lngLat: [135.7, 35.0],
      fromLngLat: [139.7, 35.7],
      arrival: day.arrival!,
    }),
  ).toBeNull();
});

test("adding another city makes a multi-city trip sent with its stops", async () => {
  const sent: unknown[] = [];
  const stored: Trip[] = [];
  const client = createFakeClient({
    "GET /v1/trips": () => stored,
    "GET /v1/destinations/search": ({ params }: { params: Record<string, unknown> }) => ({
      query: String(params.q),
      external: { state: "not_requested", results: [] },
      results: String(params.q).startsWith("Sal")
        ? [makeDestination({ ref: "900102", name: "Salzburg", admin1_name: "Salzburg" })]
        : [makeDestination()],
    }),
    "POST /v1/trips": ({ body }: { body: unknown }) => {
      sent.push(body);
      stored.unshift(routeTrip());
      return routeTrip();
    },
    "POST /v1/trips/{trip_id}/itineraries/generate": () => ({
      generation_id: "g",
      distinct: true,
      jaccard_permille: 400,
      max_jaccard_permille: 600,
      notes: [],
      itineraries: [makeItinerary("essentials"), makeItinerary("wider")],
    }),
    "GET /v1/trips/{trip_id}/itineraries": () => [makeSummary("essentials"), makeSummary("wider")],
  } as never);
  await render(
    <Harness client={client} initial={{ name: "createTrip" }}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  await fireEvent.press(await screen.findByText("Vienna", {}, { timeout: 5000 }));
  await fireEvent.press(await screen.findByTestId("add-city"));
  await fireEvent.changeText(
    await screen.findByTestId("city-search-input", {}, { timeout: 5000 }),
    "Salz",
  );
  await fireEvent.press(await screen.findByTestId("city-result-900102", {}, { timeout: 5000 }));
  // Three days by default, split 2 and 1; the list says so.
  expect(await screen.findByTestId("stop-total", {}, { timeout: 5000 })).toHaveTextContent(
    "2 cities · 3 days in all",
  );
  await fireEvent.press(screen.getByTestId("stop-1-up")); // Salzburg first
  await fireEvent.press(screen.getByTestId("stop-1-more")); // Vienna 2 days
  await fireEvent.press(screen.getByTestId("plan-trip"));
  await screen.findByTestId("plan-essentials", {}, { timeout: 10000 });
  expect(sent).toEqual([
    {
      title: "Multi-city trip",
      destination_kind: "route",
      stops: [
        { city_id: 900102, days: 1 },
        { city_id: 900101, days: 3 },
      ],
      duration_days: 4,
      start_date: null,
      uses_car: true,
    },
  ]);
});

test("editing the cities of a planned trip opens the preview of the change", async () => {
  const previews: unknown[] = [];
  let previewed: unknown = null;
  const client = createFakeClient({
    "GET /v1/trips": () => [routeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "POST /v1/trips/{trip_id}/stops/preview": ({ body }: { body: unknown }) => {
      previews.push(body);
      previewed = {
        id: CHANGE_ID,
        itinerary_id: ESSENTIALS_ID,
        action: "edit_stops",
        target_name: "Salzburg to Vienna",
        status: "pending",
        base_version: 1,
        restores_version: null,
        result_version: null,
        diff: {
          added: [],
          removed: [],
          moved: [],
          retimed: [],
          base_changes: [],
          days_changed: [1, 2, 3],
          travel_minutes_before: 0,
          travel_minutes_after: 0,
          travel_minutes_added: 0,
          estimated_legs: [],
        },
        notes: [
          {
            code: "STOPS_CHANGED",
            text: "Your cities change; the trip becomes Salzburg to Vienna.",
          },
        ],
        created_at: "2026-11-14T10:00:00Z",
        decided_at: null,
      };
      return previewed;
    },
    "GET /v1/change-sets/{change_set_id}": () => previewed,
  } as never);
  await render(
    <Harness client={client} initial={{ name: "editStops", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByTestId("stop-total", {}, { timeout: 5000 })).toHaveTextContent(
    "2 cities · 3 days in all",
  );
  expect(screen.getByTestId("save-stops")).toBeDisabled(); // nothing changed yet
  await fireEvent.press(screen.getByTestId("stop-1-up"));
  await fireEvent.press(screen.getByTestId("save-stops"));
  expect(await screen.findByText("Change your cities?", {}, { timeout: 5000 })).toBeOnTheScreen();
  expect(previews).toEqual([
    {
      stops: [
        { city_id: 900102, days: 1 },
        { city_id: 900101, days: 2 },
      ],
    },
  ]);
});

test("a plan made for the trip's earlier cities cannot be chosen", () => {
  const trip = routeTrip({ stops_version: 1 });
  expect(madeForEarlierStops(makeSummary("essentials", { stops_version: 0 }), trip)).toBe(true);
  expect(madeForEarlierStops(makeSummary("essentials", { stops_version: 1 }), trip)).toBe(false);
  expect(madeForEarlierStops(makeSummary("essentials"), makeTrip())).toBe(false);
});
