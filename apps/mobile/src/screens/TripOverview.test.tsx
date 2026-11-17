import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { captureBackButton } from "../testing/backButton";
import { createFakeClient, offline } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeItinerary,
  makePastTrip,
  makePhoto,
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
  // The header holds the name and the dates above the photo, and nothing else: no status, no
  // destination line, nothing drawn over the picture.
  expect(
    await screen.findByRole("header", { name: "Vienna. 1–2 May 2027 · 2 days." }),
  ).toBeOnTheScreen();
  expect(screen.getByTestId("trip-cover")).toBeOnTheScreen();
  expect(screen.getByText("1–2 May 2027 · 2 days")).toBeOnTheScreen();
  expect(screen.queryByText("Upcoming")).toBeNull();
  // The overview is the itinerary: its days are listed, with no "Your itineraries" block.
  expect(await screen.findByTestId("day-row-1")).toBeOnTheScreen();
  expect(screen.queryByRole("header", { name: "Your itineraries" })).toBeNull();
  // Cities, places and restaurants only: no days figure.
  expect(screen.queryByLabelText("2 days")).toBeNull();
  expect(screen.getByLabelText("2 cities")).toBeOnTheScreen();
  expect(screen.getByLabelText("2 restaurants")).toBeOnTheScreen();
  // The four tabs, Overview selected; the itinerary has no tab of its own.
  for (const name of ["Overview", "Map", "Trip photos", "Trip documents"]) {
    expect(screen.getByRole("tab", { name })).toBeOnTheScreen();
  }
  expect(screen.queryByRole("tab", { name: "Itinerary" })).toBeNull();
  expect(screen.getByRole("tab", { name: "Overview" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  expect(screen.queryByTestId("notes-planned")).toBeNull();
});

test("the original proposals are in the trip menu, not on the overview", async () => {
  const client = await open();
  await screen.findByTestId("day-row-1");
  expect(screen.queryByText("How they differ")).toBeNull();
  expect(client.count("GET /v1/trips/{trip_id}/itineraries")).toBeLessThanOrEqual(1);
  await fireEvent.press(screen.getByRole("button", { name: "Trip menu" }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Original proposals\./ }));
  expect(await screen.findByRole("header", { name: "Original proposals" })).toBeOnTheScreen();
  expect(await screen.findByTestId("plan-wider")).toBeOnTheScreen();
});

test("the trip menu opens the trip settings", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("button", { name: "Trip menu" }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Trip settings\./ }));
  expect(await screen.findByRole("header", { name: "Trip settings" })).toBeOnTheScreen();
});

test("the Overview keeps the trip header and photo and lists the days as a timeline", async () => {
  await open();
  expect(screen.getByTestId("trip-cover")).toBeOnTheScreen();
  expect(
    await screen.findByRole("button", { name: /^Day 1 · Sat 1 May\. Vienna\. / }),
  ).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: /^Day 2 · Sun 2 May\. Graz\. / })).toBeOnTheScreen();
});

test("a day of the timeline opens that day on the map, with its stops beneath", async () => {
  await open();
  await fireEvent.press(await screen.findByTestId("day-row-2"));
  expect(screen.getByRole("tab", { name: "Map" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  expect(await screen.findByText("Hofburg")).toBeOnTheScreen();
  expect(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }).props.accessibilityState).toEqual({
    selected: true,
  });
  // A stop is highlighted and the map follows; nothing opens under it. Lock and Remove are on the
  // stop's details.
  await fireEvent.press(screen.getByTestId("stop-j1"));
  expect(screen.getByTestId("stop-j1").props.accessibilityState).toMatchObject({ selected: true });
  expect(screen.queryByLabelText("Lock Hofburg")).toBeNull();
  expect(screen.getByTestId("details-j1")).toBeOnTheScreen();
});

test("Back from a stop's details returns to the same day and the same stop, not to day 1", async () => {
  await open();
  await fireEvent.press(await screen.findByTestId("day-row-2"));
  await fireEvent.press(await screen.findByTestId("stop-j1"));
  await fireEvent.press(screen.getByTestId("details-j1"));
  expect(await screen.findByTestId("place-documents")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  expect(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }).props.accessibilityState).toEqual({
    selected: true,
  });
  expect(screen.getByTestId("stop-j1").props.accessibilityState).toMatchObject({ selected: true });
});

test("the Map tab shows the map with the day's list under it, sharing the selection", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Map" }));
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  // A compact header keeps the trip's name, menu and tabs above the map.
  expect(screen.getByRole("header", { name: "Vienna" })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Trip menu" })).toBeOnTheScreen();
  // The day pills sit between the map and the stops, and are centred in each pill.
  expect(screen.getByTestId("day-tab-1")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("marker-m1"));
  expect(screen.getByTestId("stop-m1").props.accessibilityState).toMatchObject({ selected: true });
  await fireEvent.press(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }));
  expect(screen.getByLabelText(/^Transport: drive to Graz from Vienna/)).toBeOnTheScreen();
  expect(screen.getByLabelText("Stop 1, Attraction: Hofburg")).toBeOnTheScreen();
});

test("Back from the Map tab returns to the Overview, then to Trips (arrow and Android's button)", async () => {
  const back = captureBackButton();
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Map" }));
  await screen.findByTestId("map");
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByRole("tab", { name: "Overview" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  await fireEvent.press(screen.getByRole("tab", { name: "Map" }));
  await screen.findByTestId("map");
  await act(async () => {
    expect(back.press()).toBe(true);
  });
  expect(screen.getByRole("tab", { name: "Overview" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  // On the Overview, Back leaves the trip.
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText("Trips")).toBeOnTheScreen();
});

test.each(["Trip photos", "Trip documents"])(
  "Back from the %s tab leaves the trip",
  async (tab) => {
    await open();
    await fireEvent.press(await screen.findByRole("tab", { name: tab }));
    await fireEvent.press(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("header", { name: "Detour" })).toBeOnTheScreen();
  },
);

test("Photos start with no album linked; Documents start empty", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Trip photos" }));
  expect(await screen.findByTestId("albums-empty")).toBeOnTheScreen();
  expect(screen.getByTestId("link-album")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("tab", { name: "Trip documents" }));
  expect(await screen.findByText("No documents yet")).toBeOnTheScreen();
  expect(screen.getByText(/kept privately for the people on this trip/)).toBeOnTheScreen();
});

test("Back from the add-document screen returns to the Documents tab, not the overview", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Trip documents" }));
  await fireEvent.press(await screen.findByTestId("add-document"));
  expect(await screen.findByRole("header", { name: "Add document" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText("No documents yet")).toBeOnTheScreen();
  expect(
    screen.getByRole("tab", { name: "Trip documents" }).props.accessibilityState,
  ).toMatchObject({ selected: true });
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
  expect(await screen.findByRole("header", { name: "Choose a plan" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "See the proposals" }));
  expect(await screen.findByRole("header", { name: "Choose your itinerary" })).toBeOnTheScreen();
  expect(await screen.findByTestId("plan-wider")).toBeOnTheScreen();
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

test("the trip's photo hides its credit behind a small i in the corner; the days below it do not hide it", async () => {
  const client = server({
    "GET /v1/trips": () => [
      makeTrip({ selected_itinerary_id: ESSENTIALS_ID, cover_image: makePhoto() }),
    ],
  });
  await open(client);
  expect(await screen.findByTestId("day-row-1")).toBeOnTheScreen();
  expect(screen.getAllByTestId("cover-photo")[0]?.props.source.uri).toMatch(
    /^https:\/\/api\.example\.org\/v1\/images\//,
  );
  // Hidden until asked for.
  expect(screen.queryByTestId("photo-credit")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Show the photo credit" }));
  expect(screen.getByRole("link", { name: /Jane Doe, CC BY-SA 4.0/ })).toBeOnTheScreen();
  expect(screen.getAllByTestId("cover-photo")[0]).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Hide the photo credit" })).toBeOnTheScreen();
});

test("a past trip's overview offers no way to change the plan (ADR 006, 2026-11-17)", async () => {
  await open(
    server({
      "GET /v1/trips": () => [makeTrip({ status: "past", selected_itinerary_id: ESSENTIALS_ID })],
    }),
  );
  expect(await screen.findByTestId("day-row-1")).toBeOnTheScreen();
  expect(screen.queryByTestId("itinerary-optimize")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Trip menu" }));
  expect(await screen.findByTestId("menu-settings")).toBeOnTheScreen();
  for (const id of ["menu-optimize", "menu-undo-optimize", "menu-stays", "menu-proposals"]) {
    expect(screen.queryByTestId(id)).toBeNull();
  }
  // Export and the phone-only cover stay.
  expect(screen.getByTestId("menu-export")).toBeOnTheScreen();
  expect(screen.getByTestId("menu-change-photo")).toBeOnTheScreen();
});
