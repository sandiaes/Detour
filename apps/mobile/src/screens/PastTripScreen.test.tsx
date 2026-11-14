import { fireEvent, render, screen, within } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createMemoryStore } from "../cache/store";
import { type FakeHandler, createFakeClient } from "../testing/fakeClient";
import {
  TRIP_ID,
  makeArchiveInfo,
  makeArchivedVisits,
  makePastTrip,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { __mock as maplibre } from "../testing/maplibreMock";

const past = { name: "pastTrip", tripId: TRIP_ID } as const;

beforeEach(() => maplibre.reset());

function server(visits = makeArchivedVisits(), extra: Record<string, unknown> = {}) {
  const state = { visits };
  const client = createFakeClient({
    "GET /v1/trips": () => [makePastTrip()],
    "GET /v1/trips/{trip_id}/visits": () => state.visits,
    "GET /v1/trips/{trip_id}/archive": () =>
      makeArchiveInfo({ skipped: state.visits.filter((v) => !v.confirmed).length }),
    "PATCH /v1/trips/{trip_id}/visits/{visit_id}": (({ params, body }) => {
      const confirmed = (body as { confirmed: boolean }).confirmed;
      state.visits = state.visits.map((v) => (v.id === params.visit_id ? { ...v, confirmed } : v));
      return state.visits.find((v) => v.id === params.visit_id);
    }) satisfies FakeHandler,
    ...extra,
  } as never);
  return client;
}

async function open(client = server(), cache = createMemoryStore()) {
  await render(
    <Harness client={client} cache={cache} initial={past}>
      <AppContent />
    </Harness>,
  );
  return client;
}

const markers = () => screen.queryAllByTestId(/^marker-/);

test("a past trip opens on a map with a marker for each visited city and attraction", async () => {
  await open();
  expect(await screen.findByText("2 cities and 3 attractions visited")).toBeOnTheScreen();
  expect(
    screen.getByText("Sat 1 May to Tue 4 May 2027 · 4 days", { exact: false }),
  ).toBeOnTheScreen();
  expect(markers()).toHaveLength(5);
  expect(screen.getByLabelText("City, day 1: Graz")).toBeOnTheScreen();
  expect(screen.getByLabelText("Attraction, day 2: Kunsthaus Graz")).toBeOnTheScreen();
  expect(screen.getByLabelText("City, day 3: Leoben")).toBeOnTheScreen();
  // The style comes from the backend and the credit is visible, as on every map.
  expect(maplibre.map?.mapStyle).toBe("https://tiles.example.org/styles/test");
  expect(screen.getByText("Data from OpenStreetMap")).toBeOnTheScreen();
});

test("the map has no routes: no line layer, no source, no travel time anywhere", async () => {
  await open();
  await screen.findByText("2 cities and 3 attractions visited");
  expect(maplibre.layers).toEqual([]);
  expect(maplibre.sources).toEqual({});
  expect(screen.queryByText(/walk|drive|routed|estimated/i)).toBeNull();
  expect(screen.getByText(/Routes and travel times are not kept/)).toBeOnTheScreen();
});

test("tapping a marker shows its name, kind and day", async () => {
  await open();
  await fireEvent.press(await screen.findByTestId("marker-v-leoben"));
  expect(screen.getAllByText("Leoben").length).toBeGreaterThan(0);
  expect(screen.getByText("City · day 3")).toBeOnTheScreen();
});

test("the list is grouped by city, each city once, with the attractions by day", async () => {
  await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the list by city" }));
  expect(screen.getByRole("header", { name: "Graz" })).toBeOnTheScreen();
  expect(screen.getByRole("header", { name: "Leoben" })).toBeOnTheScreen();
  expect(screen.getAllByText("Graz")).toHaveLength(1);
  expect(screen.getByText("City · visited · 2 attractions")).toBeOnTheScreen();
  expect(screen.getByText("City · visited · 1 attraction")).toBeOnTheScreen();
  expect(screen.getByText("Day 1 · Sat 1 May")).toBeOnTheScreen();
  expect(screen.getByText("Day 2 · Sun 2 May")).toBeOnTheScreen();
  expect(screen.getByText("Day 3 · Mon 3 May")).toBeOnTheScreen();
  expect(screen.queryByText(/walk|drive|routed|estimated/i)).toBeNull();
});

test("a visit that was skipped can be cleared, leaves the map, and can be restored", async () => {
  const client = await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the list by city" }));
  await fireEvent.press(screen.getByRole("button", { name: "Mark Kunsthaus Graz as skipped" }));
  expect(await screen.findByText("Day 2 · Sun 2 May · skipped")).toBeOnTheScreen();
  expect(screen.getByText("2 cities and 2 attractions visited")).toBeOnTheScreen();
  expect(screen.getByText("1 visit marked as skipped")).toBeOnTheScreen();
  expect(client.calls.filter((c) => c.method === "PATCH")).toEqual([
    expect.objectContaining({
      params: expect.objectContaining({ trip_id: TRIP_ID, visit_id: "v-kunsthaus" }),
      body: { confirmed: false },
    }),
  ]);

  await fireEvent.press(screen.getByRole("tab", { name: "Show the map" }));
  expect(markers()).toHaveLength(4);
  expect(screen.queryByTestId("marker-v-kunsthaus")).toBeNull();

  await fireEvent.press(screen.getByRole("tab", { name: "Show the list by city" }));
  await fireEvent.press(
    screen.getByRole("button", { name: "Mark Kunsthaus Graz as visited again" }),
  );
  expect(await screen.findByText("2 cities and 3 attractions visited")).toBeOnTheScreen();
  expect(screen.queryByText(/marked as skipped/)).toBeNull();
});

test("a city can be cleared too", async () => {
  const client = await open();
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the list by city" }));
  await fireEvent.press(screen.getByRole("button", { name: "Mark Leoben as skipped" }));
  expect(await screen.findByText("1 city and 3 attractions visited")).toBeOnTheScreen();
  expect(client.count("PATCH /v1/trips/{trip_id}/visits/{visit_id}")).toBe(1);
});

test("the size of what is stored is shown", async () => {
  await open();
  expect(await screen.findByText(/Stored: 4\.5 kB\./)).toBeOnTheScreen();
});

test("a past trip needs no plan, route or travel-time request", async () => {
  const client = await open();
  await screen.findByText("2 cities and 3 attractions visited");
  await fireEvent.press(screen.getByRole("tab", { name: "Show the list by city" }));
  const paths = new Set(client.calls.map((c) => `${c.method} ${c.path}`));
  expect([...paths].sort()).toEqual([
    "GET /v1/trips",
    "GET /v1/trips/{trip_id}/archive",
    "GET /v1/trips/{trip_id}/visits",
  ]);
});

test("when every visit is skipped the map says so and offers the list", async () => {
  const visits = makeArchivedVisits().map((v) => ({ ...v, confirmed: false }));
  await open(server(visits));
  expect(await screen.findByText("Every visit is marked as skipped")).toBeOnTheScreen();
  expect(screen.getByText("5 visits marked as skipped")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Show the list" }));
  expect(
    await screen.findByRole("button", { name: "Mark Graz as visited again" }),
  ).toBeOnTheScreen();
});

test("an archive with no visits says nothing was kept", async () => {
  await open(server([]));
  expect(await screen.findByText("Nothing was kept")).toBeOnTheScreen();
});

test("attractions without a city row are listed under the destination", async () => {
  const visits = makeArchivedVisits().filter((v) => v.kind === "attraction");
  await open(server(visits));
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the list by city" }));
  expect(screen.getByText("Styria")).toBeOnTheScreen();
  expect(screen.getByText("Destination · 3 attractions")).toBeOnTheScreen();
});

test("offline, a past trip is read from the device: the list works, the map says it needs a connection", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makePastTrip()]);
  await cache.set(`visits:${TRIP_ID}`, makeArchivedVisits());
  await render(
    <Harness state={{ phase: "error", message: "x" }} cache={cache} initial={past}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("The map needs a connection")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Show the list" }));
  expect(await screen.findByText("Kunsthaus Graz")).toBeOnTheScreen();
  // Clearing a visit needs the server: the control is off rather than failing silently.
  expect(screen.getByRole("button", { name: "Mark Kunsthaus Graz as skipped" })).toBeDisabled();
});

test("a failed change is reported and the visit stays as it was", async () => {
  const client = server(makeArchivedVisits(), {
    "PATCH /v1/trips/{trip_id}/visits/{visit_id}": () => ({
      status: 404,
      body: { code: "not_found", detail: "no such visit" },
    }),
  });
  await open(client);
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the list by city" }));
  await fireEvent.press(screen.getByRole("button", { name: "Mark Schlossberg as skipped" }));
  expect(await screen.findByText(/That item no longer exists/)).toBeOnTheScreen();
  expect(screen.queryByText(/marked as skipped/)).toBeNull();
});

test("the trip settings of a past trip offer deleting only", async () => {
  await open();
  await fireEvent.press(await screen.findByTestId("trip-settings"));
  expect(await screen.findByRole("header", { name: "Trip settings" })).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Get new proposals" })).toBeNull();
  expect(screen.queryByTestId("archive-trip")).toBeNull();
  expect(screen.getByTestId("delete-trip")).toBeOnTheScreen();
});

test("a past trip in the list opens its places, not a plan", async () => {
  const client = server(makeArchivedVisits(), {
    "GET /v1/trips": () => [makePastTrip(), makeTrip({ id: "t2", title: "Prague" })],
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByRole("tab", { name: "Past" }));
  const card = await screen.findByRole("button", { name: /Styria trip\..*Past\./ });
  expect(within(card).getByText("Past")).toBeOnTheScreen();
  expect(screen.queryByText("Prague")).toBeNull();
  await fireEvent.press(card);
  expect(await screen.findByText("2 cities and 3 attractions visited")).toBeOnTheScreen();
});

test("a past trip reached through the trip route shows the same view", async () => {
  await render(
    <Harness client={server()} initial={{ name: "trip", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("2 cities and 3 attractions visited")).toBeOnTheScreen();
});
