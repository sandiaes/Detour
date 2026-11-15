import type { Stay } from "@detour/shared";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

jest.setTimeout(30_000);

// Where the traveller sleeps (ADR 030): the list, adding a stay for a range of days, and the
// morning leg a day shows. The server's answers are faked.

const stay = (over: Partial<Stay> = {}): Stay => ({
  id: "stay-1",
  trip_id: TRIP_ID,
  name: "Hotel Alpen",
  lat: 48.2,
  lon: 16.37,
  first_day: 1,
  last_day: 1,
  created_at: "2026-11-15T10:00:00Z",
  ...over,
});

async function show(handlers: Record<string, unknown>) {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ duration_days: 3 })],
    ...handlers,
  } as never);
  await render(
    <Harness client={client} initial={{ name: "stays", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("the stays are listed with their days", async () => {
  await show({
    "GET /v1/trips/{trip_id}/stays": () => [
      stay(),
      stay({ id: "s2", name: "Pension", first_day: 2, last_day: 3 }),
    ],
  });
  expect(await screen.findByText("Hotel Alpen")).toBeTruthy();
  expect(screen.getByText("Day 1")).toBeTruthy();
  expect(screen.getByText("Days 2 to 3")).toBeTruthy();
});

test("a stay is added for the days that have none, from a place found by search", async () => {
  const bodies: unknown[] = [];
  await show({
    "GET /v1/trips/{trip_id}/stays": () => [stay()],
    "GET /v1/places/search": () => ({
      query: "alpen",
      results: [],
      external: {
        state: "ok",
        results: [
          {
            provider: "photon",
            ref: "n1",
            name: "Hotel Seeblick",
            lat: 47.5,
            lon: 13.6,
            city: "Hallstatt",
          },
        ],
      },
    }),
    "POST /v1/trips/{trip_id}/stays": ({ body }: { body: unknown }) => {
      bodies.push(body);
      return stay({ id: "new" });
    },
  });
  await fireEvent.press(await screen.findByTestId("stay-add"));
  await fireEvent.changeText(screen.getByTestId("stay-search"), "seeblick");
  await fireEvent.press(await screen.findByText("Hotel Seeblick"));
  await fireEvent.press(screen.getByTestId("stay-save"));
  expect(bodies).toEqual([
    { name: "Hotel Seeblick", lat: 47.5, lon: 13.6, first_day: 2, last_day: 3 },
  ]);
});

test("a day with a stay says how the morning goes", async () => {
  const plan = makeItinerary("essentials", { status: "selected" });
  const first = plan.days[0]!.items[0]!;
  plan.days[0]!.start = {
    stay_id: "stay-1",
    name: "Hotel Alpen",
    lat: 48.2,
    lon: 16.37,
    to_item_id: first.id,
    mode: "walk",
    seconds: 600,
    meters: 800,
    confidence: "estimated",
  };
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": () => plan,
  } as never);
  await render(
    <Harness
      client={client}
      initial={{
        name: "itinerary",
        tripId: TRIP_ID,
        itineraryId: ESSENTIALS_ID,
        view: "days",
        day: 1,
      }}
    >
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByTestId("stay-start")).toBeTruthy();
  expect(screen.getByText(/Walk from Hotel Alpen · 10 min · 800 m/)).toBeTruthy();
});

test("a stay can be pinned: the coordinates and a name, then the days", async () => {
  const bodies: unknown[] = [];
  await show({
    "GET /v1/trips/{trip_id}/stays": () => [],
    "POST /v1/trips/{trip_id}/stays": ({ body }: { body: unknown }) => {
      bodies.push(body);
      return stay({ id: "new" });
    },
  });
  await fireEvent.press(await screen.findByTestId("stay-add"));
  await fireEvent.press(await screen.findByText("Pin on map"));
  await fireEvent.changeText(screen.getByLabelText("Latitude"), "47,5");
  await fireEvent.changeText(screen.getByLabelText("Longitude"), "13.6");
  await fireEvent.changeText(screen.getByLabelText("Name"), "Airbnb");
  await fireEvent.press(screen.getByTestId("stay-use-pin"));
  await fireEvent.press(screen.getByTestId("stay-save"));
  expect(bodies).toEqual([{ name: "Airbnb", lat: 47.5, lon: 13.6, first_day: 1, last_day: 3 }]);
});
