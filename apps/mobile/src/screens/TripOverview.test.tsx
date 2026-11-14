import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient, offline } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeItinerary,
  makePastTrip,
  makeArchiveInfo,
  makeArchivedVisits,
  makeSummary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { previewDays } from "./TripOverviewScreen";

const overview = { name: "tripOverview", tripId: TRIP_ID } as const;

function server(handlers: Record<string, unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: "selected" }),
      makeSummary("wider"),
    ],
    ...handlers,
  } as never);
}

async function open(
  client = server(),
  initial: Parameters<typeof Harness>[0]["initial"] = overview,
) {
  await render(
    <Harness client={client} initial={initial}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("the overview shows the cover, status, figures and the active itinerary", async () => {
  await open();
  expect(await screen.findByRole("header", { name: "Vienna" })).toBeOnTheScreen();
  expect(screen.getByTestId("trip-cover")).toBeOnTheScreen();
  expect(screen.getByText("Upcoming")).toBeOnTheScreen();
  expect(screen.getByText("1–2 May 2027 · 2 days")).toBeOnTheScreen();
  expect(await screen.findByRole("header", { name: "Your itinerary" })).toBeOnTheScreen();
  // Cities, places and restaurants only: no days figure.
  expect(screen.queryByLabelText("2 days")).toBeNull();
  expect(screen.getByLabelText("2 cities")).toBeOnTheScreen();
  expect(screen.getByLabelText("2 restaurants")).toBeOnTheScreen();
  // The five tabs, Overview selected.
  for (const name of ["Overview", "Itinerary", "Map", "Trip photos", "Trip documents"]) {
    expect(screen.getByRole("tab", { name })).toBeOnTheScreen();
  }
  expect(screen.getByRole("tab", { name: "Overview" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  // No first days and no notes placeholder: the days are in the Itinerary tab.
  expect(screen.queryByRole("button", { name: /^Day 1 · Sat 1 May/ })).toBeNull();
  expect(screen.queryByTestId("notes-planned")).toBeNull();
});

test("the original proposals are in the trip menu, not on the overview", async () => {
  const client = await open();
  await screen.findByRole("header", { name: "Your itinerary" });
  expect(screen.queryByText("How they differ")).toBeNull();
  expect(client.count("GET /v1/trips/{trip_id}/itineraries")).toBe(0);
  await fireEvent.press(screen.getByRole("button", { name: "Trip menu" }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Original proposals\./ }));
  expect(await screen.findByRole("header", { name: "Original proposals" })).toBeOnTheScreen();
  expect(await screen.findByText("How they differ")).toBeOnTheScreen();
});

test("the trip menu opens the trip settings", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("button", { name: "Trip menu" }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Trip settings\./ }));
  expect(await screen.findByRole("header", { name: "Trip settings" })).toBeOnTheScreen();
});

test("the Itinerary tab lists the days as a timeline without the trip header", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Itinerary" }));
  expect(screen.queryByTestId("trip-cover")).toBeNull();
  expect(
    await screen.findByRole("button", { name: /^Day 1 · Sat 1 May\. Vienna\. / }),
  ).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: /^Day 2 · Sun 2 May\. Graz\. / })).toBeOnTheScreen();
});

test("a day of the timeline opens that day on the map, with its stops beneath", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Itinerary" }));
  await fireEvent.press(await screen.findByTestId("day-row-2"));
  expect(screen.getByRole("tab", { name: "Map" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  expect(await screen.findByText("Hofburg")).toBeOnTheScreen();
  expect(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }).props.accessibilityState).toEqual({
    selected: true,
  });
  // A stop opens its details and can be locked or removed, as before.
  await fireEvent.press(screen.getByTestId("stop-j1"));
  expect(screen.getByLabelText("Lock Hofburg")).toBeOnTheScreen();
});

test("the Map tab shows the map with the day's list under it, sharing the selection", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Map" }));
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  // A compact header keeps the trip's name, menu and tabs above the map.
  expect(screen.getByRole("header", { name: "Vienna" })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Trip menu" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("marker-m1"));
  expect(screen.getByTestId("stop-m1").props.accessibilityState).toMatchObject({ selected: true });
  await fireEvent.press(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }));
  expect(screen.getByLabelText(/^Transport: drive to Graz from Vienna/)).toBeOnTheScreen();
  expect(screen.getByLabelText("Stop 1, Attraction: Hofburg")).toBeOnTheScreen();
});

test("Photos say plainly that they are not built yet; Documents start empty", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Trip photos" }));
  expect(screen.getByTestId("trip-photos-planned")).toBeOnTheScreen();
  expect(screen.getByText(/Google Photos is not built yet/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("tab", { name: "Trip documents" }));
  expect(await screen.findByText("No documents yet")).toBeOnTheScreen();
  expect(screen.getByText(/stay on this phone only/)).toBeOnTheScreen();
});

test("a trip with no plan leads to the proposals", async () => {
  await open(
    server({
      "GET /v1/trips": () => [makeTrip()],
      "GET /v1/trips/{trip_id}/itineraries": () => [
        makeSummary("essentials"),
        makeSummary("wider"),
      ],
    }),
  );
  expect(await screen.findByText("Planning")).toBeOnTheScreen();
  expect(screen.getByRole("header", { name: "Choose a plan" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "See the proposals" }));
  expect(await screen.findByRole("header", { name: "Proposals" })).toBeOnTheScreen();
  expect(await screen.findByText("How they differ")).toBeOnTheScreen();
});

test("an itinerary that cannot be loaded offline says so and offers another try", async () => {
  await open(server({ "GET /v1/itineraries/{itinerary_id}": offline }));
  expect(await screen.findByText("You are offline")).toBeOnTheScreen();
  expect(screen.getByText(/not saved on the device yet/)).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Try again" })).toBeOnTheScreen();
});

test("a trip that no longer exists says so", async () => {
  await open(server({ "GET /v1/trips": () => [] }));
  expect(await screen.findByText("Trip not found")).toBeOnTheScreen();
});

test("a past trip reached through the overview shows its visited places (ADR 006)", async () => {
  await open(
    createFakeClient({
      "GET /v1/trips": () => [makePastTrip()],
      "GET /v1/trips/{trip_id}/visits": () => makeArchivedVisits(),
      "GET /v1/trips/{trip_id}/archive": () => makeArchiveInfo(),
    }),
  );
  expect(await screen.findByText("2 cities and 3 attractions visited")).toBeOnTheScreen();
});

test("previewDays starts at today's day during the trip", () => {
  const trip = makeTrip({ selected_itinerary_id: ESSENTIALS_ID });
  const plan = makeItinerary("essentials");
  expect(previewDays(trip, plan, "2027-04-01").map((d) => d.day_index)).toEqual([1, 2]);
  expect(previewDays(trip, plan, "2027-05-02").map((d) => d.day_index)).toEqual([2]);
  expect(previewDays(trip, plan, "2027-05-01", 1).map((d) => d.day_index)).toEqual([1]);
});
