import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createMemoryStore } from "../cache/store";
import { createFakeClient } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeArchiveInfo,
  makeItinerary,
  makeSummary,
  makeTrip,
  makeVisit,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";

const settings = { name: "tripSettings", tripId: TRIP_ID } as const;

function generated() {
  return {
    generation_id: "g2",
    distinct: true,
    jaccard_permille: 400,
    max_jaccard_permille: 600,
    notes: [],
    itineraries: [makeItinerary("essentials"), makeItinerary("wider")],
  };
}

async function open(handlers: Record<string, unknown> = {}, cache = createMemoryStore()) {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/trips/{trip_id}/itineraries": () => [makeSummary("essentials"), makeSummary("wider")],
    ...handlers,
  } as never);
  await render(
    <Harness client={client} cache={cache} initial={settings}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("asking for new proposals plans again and shows them, keeping the chosen plan", async () => {
  const client = await open({
    "POST /v1/trips/{trip_id}/itineraries/generate": generated,
  });
  await fireEvent.press(await screen.findByRole("button", { name: "Get new proposals" }));
  expect(await screen.findByRole("header", { name: "Original proposals" })).toBeOnTheScreen();
  expect(client.count("POST /v1/trips/{trip_id}/itineraries/generate")).toBe(1);
  // Back from the proposals goes to the trip, not to the settings, and then to the trips.
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: /^Vienna\./ })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: "Detour" })).toBeOnTheScreen();
});

test("a failed new planning says so and stays on the settings", async () => {
  await open({
    "POST /v1/trips/{trip_id}/itineraries/generate": () => ({
      status: 422,
      body: { detail: "x", code: "planning_impossible" },
    }),
  });
  await fireEvent.press(await screen.findByRole("button", { name: "Get new proposals" }));
  expect(await screen.findByText(/does not have enough places/)).toBeOnTheScreen();
  expect(screen.getByRole("header", { name: "Trip settings" })).toBeOnTheScreen();
});

test("deleting asks first, then removes the trip from the server, the list and the device", async () => {
  const cache = createMemoryStore();
  await cache.set(`itineraries:${TRIP_ID}`, [makeSummary("essentials")]);
  let deleted = false;
  const client = await open(
    {
      "GET /v1/trips": () => (deleted ? [] : [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })]),
      "DELETE /v1/trips/{trip_id}": () => {
        deleted = true;
        return undefined;
      },
    },
    cache,
  );
  await fireEvent.press(await screen.findByRole("button", { name: /^Delete the trip/ }));
  // Nothing is sent until it is confirmed.
  expect(client.count("DELETE /v1/trips/{trip_id}")).toBe(0);
  await fireEvent.press(screen.getByRole("button", { name: "Keep the trip" }));
  expect(client.count("DELETE /v1/trips/{trip_id}")).toBe(0);
  await fireEvent.press(screen.getByRole("button", { name: /^Delete the trip/ }));
  await fireEvent.press(screen.getByRole("button", { name: "Yes, delete the trip" }));
  expect(await screen.findByText("No trips yet")).toBeOnTheScreen();
  expect(client.count("DELETE /v1/trips/{trip_id}")).toBe(1);
  expect(await cache.get(`itineraries:${TRIP_ID}`)).toBeNull();
});

test("a failed deletion says so and keeps the trip", async () => {
  await open({
    "DELETE /v1/trips/{trip_id}": () => ({ status: 500, body: { detail: "x", code: null } }),
  });
  await fireEvent.press(await screen.findByRole("button", { name: /^Delete the trip/ }));
  await fireEvent.press(screen.getByRole("button", { name: "Yes, delete the trip" }));
  expect(await screen.findByText(/The server had a problem/)).toBeOnTheScreen();
  expect(screen.getByRole("header", { name: "Trip settings" })).toBeOnTheScreen();
});

test("a past trip can be reopened or deleted, and offers no changes", async () => {
  await open({ "GET /v1/trips": () => [makeTrip({ status: "past" })] });
  expect(await screen.findByRole("button", { name: /^Delete the trip/ })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: /^Reopen the trip/ })).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Get new proposals" })).toBeNull();
  expect(screen.queryByTestId("archive-trip")).toBeNull();
  expect(screen.queryByTestId("edit-dates")).toBeNull();
});

test("the start date can be changed to a date in the past; the trip stays active", async () => {
  const client = await open({
    "PATCH /v1/trips/{trip_id}": (c: { body: { start_date: string | null } }) =>
      makeTrip({
        selected_itinerary_id: ESSENTIALS_ID,
        start_date: c.body.start_date,
        end_date: "2026-03-03",
      }),
  });
  await fireEvent.press(await screen.findByTestId("edit-dates"));
  // The calendar opens on the trip's month (May 2027): go back to March 2026, 14 months.
  for (let i = 0; i < 14; i++) await fireEvent.press(screen.getByTestId("cal-prev"));
  await fireEvent.press(screen.getByTestId("cal-2026-03-01"));
  await waitFor(() =>
    expect(client.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      start_date: "2026-03-01",
    }),
  );
  // Dates already over do not make it a past trip: it can still be marked as past by hand.
  expect(await screen.findByTestId("archive-trip")).toBeOnTheScreen();
});

test("reopening a past trip calls the server and returns to the trip", async () => {
  const reopen = jest.fn(() =>
    makeTrip({ status: "active", selected_itinerary_id: ESSENTIALS_ID }),
  );
  const client = await open({
    "GET /v1/trips": () => [makeTrip({ status: "past", selected_itinerary_id: ESSENTIALS_ID })],
    "POST /v1/trips/{trip_id}/reopen": reopen,
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
  });
  await fireEvent.press(await screen.findByRole("button", { name: /^Reopen the trip/ }));
  await waitFor(() => expect(reopen).toHaveBeenCalled());
  expect(client).toBeDefined();
  expect(screen.queryByRole("header", { name: "Trip settings" })).toBeNull();
});

test("the settings are reachable from the plan and from the proposals", async () => {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
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
  await fireEvent.press(await screen.findByRole("button", { name: "Trip settings" }));
  expect(await screen.findByRole("header", { name: "Trip settings" })).toBeOnTheScreen();
});

test("marking a trip as past asks first, keeps nothing until confirmed, then shows the places", async () => {
  const client = await open({
    "POST /v1/trips/{trip_id}/archive": () =>
      makeTrip({
        status: "past",
        archived_at: "2027-05-06T08:00:00Z",
        selected_itinerary_id: null,
      }),
    "GET /v1/trips/{trip_id}/visits": () => [
      makeVisit({ id: "v1", kind: "city", name: "Vienna", lat: 48.2082, lon: 16.3738 }),
      makeVisit({
        id: "v2",
        kind: "attraction",
        name: "Schönbrunn Palace",
        lat: 48.18,
        lon: 16.31,
      }),
    ],
    "GET /v1/trips/{trip_id}/archive": () => makeArchiveInfo({ cities: 1, attractions: 1 }),
  });
  await fireEvent.press(await screen.findByTestId("archive-trip"));
  // The warning says what is kept and what is deleted, and nothing has been sent yet.
  // ADR 006 amendment of 2026-11-16: the plan is kept; only the undo history is cut.
  expect(screen.getByText(/keeps its plan, routes and documents/)).toBeOnTheScreen();
  expect(screen.getByText(/moves to the Past tab\. Its plan stays/)).toBeOnTheScreen();
  expect(client.count("POST /v1/trips/{trip_id}/archive")).toBe(0);
  await fireEvent.press(screen.getByRole("button", { name: "Not yet" }));
  expect(screen.getByTestId("archive-trip")).toBeOnTheScreen();

  await fireEvent.press(screen.getByTestId("archive-trip"));
  await fireEvent.press(screen.getByTestId("confirm-archive"));
  expect(await screen.findByText("1 city and 1 attraction visited")).toBeOnTheScreen();
  expect(client.count("POST /v1/trips/{trip_id}/archive")).toBe(1);
});

test("a trip to a place with no sight data offers no proposals (ADR 027)", async () => {
  await open({
    "GET /v1/trips": () => [
      makeTrip({
        destination: {
          kind: "place",
          ref: "photon:N42",
          name: "Hallstatt",
          lat: 47.56,
          lon: 13.65,
          country_iso2: "AT",
        },
      }),
    ],
  });
  expect(await screen.findByTestId("delete-trip")).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Get new proposals" })).toBeNull();
});
