import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createMemoryStore } from "../cache/store";
import { createFakeClient, offline } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeArchiveInfo,
  makeItinerary,
  makePastTrip,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";

const trips = (list = [makeTrip()]) => ({ "GET /v1/trips": () => list });

test("a first run with no trips explains what to do and offers the form", async () => {
  const client = createFakeClient(trips([]));
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("No trips yet")).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Plan a trip"));
  expect(await screen.findByRole("header", { name: "New trip" })).toBeOnTheScreen();
});

test("trips are listed with destination, dates, status and what the plan contains", async () => {
  const client = createFakeClient({
    ...trips([
      makeTrip(),
      makeTrip({
        id: "t2",
        title: "Prague",
        selected_itinerary_id: ESSENTIALS_ID,
        start_date: null,
        end_date: null,
        duration_days: 3,
      }),
    ]),
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(screen.getByText("1–2 May 2027 · 2 days")).toBeOnTheScreen();
  expect(screen.getByText("Planning")).toBeOnTheScreen();
  expect(screen.getByText("Vienna · No plan chosen yet")).toBeOnTheScreen();
  expect(screen.getAllByText("Upcoming")).toHaveLength(2); // the tab and the badge
  expect(screen.queryByRole("tab", { name: "Archived" })).toBeNull();
  // The counts come from the active plan, read once and shared with the plan screen.
  expect(
    await screen.findByText(/^Vienna · 2 cities · \d+ places · \d+ restaurants$/),
  ).toBeOnTheScreen();
  expect(client.count("GET /v1/itineraries/{itinerary_id}")).toBe(1);
  // The whole card is one control with a full spoken description.
  expect(
    screen.getByRole("button", {
      name: /^Prague\. Vienna\. 3 days\. Upcoming\. 2 cities · /,
    }),
  ).toBeOnTheScreen();
});

test("the tabs split upcoming and past trips", async () => {
  const client = createFakeClient({
    ...trips([makeTrip(), makePastTrip({ id: "p1", title: "Graz last spring" })]),
    "GET /v1/trips/{trip_id}/archive": () => makeArchiveInfo(),
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(screen.queryByText("Graz last spring")).toBeNull();
  expect(screen.getByRole("tab", { name: "Upcoming" }).props.accessibilityState).toMatchObject({
    selected: true,
  });

  await fireEvent.press(screen.getByRole("tab", { name: "Past" }));
  expect(await screen.findByText("Graz last spring")).toBeOnTheScreen();
  expect(screen.queryByText("Vienna, 2 days")).toBeNull();
  // A past trip keeps its cities and attractions, not its restaurants (ADR 006).
  expect(await screen.findByText(/· 2 cities · 3 places$/)).toBeOnTheScreen();
});

test("each interactive control is at least 48 dp tall", async () => {
  await render(
    <Harness client={createFakeClient(trips())}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText("Vienna, 2 days");
  const newTrip = screen.getByRole("button", { name: "New trip" });
  const flat = Array.isArray(newTrip.props.style)
    ? Object.assign({}, ...newTrip.props.style.flat(3).filter(Boolean))
    : newTrip.props.style;
  expect(flat.minHeight).toBeGreaterThanOrEqual(48);
});

test("while the free host wakes and nothing is saved, a clear waking state is shown", async () => {
  await render(
    <Harness state={{ phase: "connecting", waking: true }}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Waking the server")).toBeOnTheScreen();
  expect(screen.getByText(/can take about a minute/)).toBeOnTheScreen();
  expect(screen.getByText(/Waiting \d+ s/)).toBeOnTheScreen();
});

test("while waking, saved trips are shown with a notice instead of a spinner", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makeTrip()]);
  await render(
    <Harness state={{ phase: "connecting", waking: true }} cache={cache}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(screen.getByText(/The free host is starting up/)).toBeOnTheScreen();
});

test("offline with a saved copy: the trips can be read and the notice says so", async () => {
  const cache = createMemoryStore(() => Date.now() - 5 * 60_000);
  await cache.set("trips", [makeTrip()]);
  const client = createFakeClient({ "GET /v1/trips": offline });
  await render(
    <Harness client={client} cache={cache}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(await screen.findByText(/Showing trips saved 5 minutes ago/)).toBeOnTheScreen();
  expect(screen.getByText(/changes need a connection/)).toBeOnTheScreen();
});

test("the backend being unreachable is the same offline read", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makeTrip()]);
  await render(
    <Harness state={{ phase: "error", message: "Health check failed" }} cache={cache}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(await screen.findByText(/Showing trips saved/)).toBeOnTheScreen();
});

test("offline with nothing saved says so and offers another try", async () => {
  const client = createFakeClient({ "GET /v1/trips": offline });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("You are offline")).toBeOnTheScreen();
  expect(screen.getByText(/No trips are saved on this device yet/)).toBeOnTheScreen();
  expect(screen.getByText("Try again")).toBeOnTheScreen();
});

test("a server error shows its message and Try again fetches again", async () => {
  let fail = true;
  const client = createFakeClient({
    "GET /v1/trips": () =>
      fail ? { status: 500, body: { detail: "boom", code: null } } : [makeTrip()],
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText(/The server had a problem/)).toBeOnTheScreen();
  fail = false;
  await fireEvent.press(screen.getByText("Try again"));
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(client.count("GET /v1/trips")).toBe(2);
});

test("coming back to the list within a minute makes no new request", async () => {
  const client = createFakeClient(trips());
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText("Vienna, 2 days");
  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await fireEvent.press(await screen.findByRole("tab", { name: "Trips" }));
  expect(await screen.findByText("Vienna, 2 days")).toBeOnTheScreen();
  expect(client.count("GET /v1/trips")).toBe(1);
});

test("opening a trip needs no further request for the trip itself", async () => {
  const client = createFakeClient({
    ...trips(),
    "GET /v1/trips/{trip_id}/itineraries": () => [],
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByText("Vienna, 2 days"));
  await fireEvent.press(await screen.findByRole("button", { name: "See the proposals" }));
  expect(await screen.findByText("Not planned yet")).toBeOnTheScreen();
  expect(client.count("GET /v1/trips")).toBe(1);
  expect(
    client.calls.find((c) => c.path === "/v1/trips/{trip_id}/itineraries")?.params.trip_id,
  ).toBe(TRIP_ID);
});

test("a trip with a chosen plan opens on its overview, built around the active itinerary", async () => {
  const client = createFakeClient({
    ...trips([makeTrip({ selected_itinerary_id: ESSENTIALS_ID })]),
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByRole("button", { name: /Upcoming/ }));
  expect(await screen.findByRole("header", { name: "Vienna, 2 days" })).toBeOnTheScreen();
  expect(await screen.findByRole("header", { name: "Your itinerary" })).toBeOnTheScreen();
  expect(screen.getByText("Essentials plan")).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: /^Day 1 · Sat 1 May\./ })).toBeOnTheScreen();
  // The original proposals are not shown, and not even fetched.
  expect(screen.queryByText("How they differ")).toBeNull();
  expect(client.count("GET /v1/trips/{trip_id}/itineraries")).toBe(0);
  // The card's counts and the overview share one read of the plan.
  expect(client.count("GET /v1/itineraries/{itinerary_id}")).toBe(1);
});

test("a trip with no chosen plan opens on its overview, which leads to the proposals", async () => {
  const client = createFakeClient({
    ...trips(),
    "GET /v1/trips/{trip_id}/itineraries": () => [],
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByRole("button", { name: /No plan chosen yet/ }));
  expect(await screen.findByRole("header", { name: "Choose a plan" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "See the proposals" }));
  expect(await screen.findByText("Not planned yet")).toBeOnTheScreen();
});
