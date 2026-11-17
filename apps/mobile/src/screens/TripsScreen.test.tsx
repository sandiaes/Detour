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
  makePhoto,
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
  await fireEvent.press(screen.getByText("New trip"));
  expect(await screen.findByRole("header", { name: "Create new trip" })).toBeOnTheScreen();
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
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(screen.getByText("1–2 May 2027 · 2 days")).toBeOnTheScreen();
  expect(screen.getByText("Planning")).toBeOnTheScreen();
  expect(screen.getAllByText("Upcoming")).toHaveLength(2); // the tab and the badge
  expect(screen.queryByRole("tab", { name: "Archived" })).toBeNull();
  // A card is the cover, the name, the dates and the length, and nothing under it: no footer, no
  // counts, and so no request for the plan.
  expect(screen.queryByText(/No plan chosen yet/)).toBeNull();
  expect(screen.queryByText(/cities/)).toBeNull();
  expect(client.count("GET /v1/itineraries/{itinerary_id}")).toBe(0);
  // The whole card is one control with a full spoken description.
  expect(
    screen.getByRole("button", { name: /^Prague\. .*3 days\. Upcoming\.$/ }),
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
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(screen.queryByText("Graz last spring")).toBeNull();
  expect(screen.getByRole("tab", { name: "Upcoming" }).props.accessibilityState).toMatchObject({
    selected: true,
  });

  await fireEvent.press(screen.getByRole("tab", { name: "Past" }));
  expect(await screen.findByText("Graz last spring")).toBeOnTheScreen();
  expect(screen.queryByText("Vienna")).toBeNull();
});

test("each interactive control is at least 48 dp tall", async () => {
  await render(
    <Harness client={createFakeClient(trips())}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText("Vienna");
  const newTrip = screen.getByRole("button", { name: "New trip" });
  const flat = Array.isArray(newTrip.props.style)
    ? Object.assign({}, ...newTrip.props.style.flat(3).filter(Boolean))
    : newTrip.props.style;
  // Drawn at 44 dp; its hit slop makes the touch 48 dp (docs/design.md, "Touch").
  const slop = newTrip.props.hitSlop ?? {};
  expect(flat.minHeight + (slop.top ?? 0) + (slop.bottom ?? 0)).toBeGreaterThanOrEqual(48);
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
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(screen.getByText(/The free host is starting up/)).toBeOnTheScreen();
});

test("offline with a saved copy: the trips can be read", async () => {
  const cache = createMemoryStore(() => Date.now() - 5 * 60_000);
  await cache.set("trips", [makeTrip()]);
  const client = createFakeClient({ "GET /v1/trips": offline });
  await render(
    <Harness client={client} cache={cache}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(screen.queryByText(/Showing trips saved/)).toBeNull();
});

test("the backend being unreachable is the same offline read", async () => {
  const cache = createMemoryStore();
  await cache.set("trips", [makeTrip()]);
  await render(
    <Harness state={{ phase: "error", message: "Health check failed" }} cache={cache}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(await screen.findByText("You’re offline")).toBeOnTheScreen();
  expect(screen.queryByText(/Showing trips saved/)).toBeNull();
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
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(client.count("GET /v1/trips")).toBe(2);
});

test("coming back to the list within a minute makes no new request", async () => {
  const client = createFakeClient(trips());
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText("Vienna");
  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await fireEvent.press(await screen.findByRole("tab", { name: "Trips" }));
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
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
  await fireEvent.press(await screen.findByText("Vienna"));
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
  expect(await screen.findByRole("header", { name: /^Vienna\./ })).toBeOnTheScreen();
  expect(await screen.findByTestId("day-row-1")).toBeOnTheScreen();
  // The comparison is not shown; the proposals are not read for it.
  expect(screen.queryByText("How they differ")).toBeNull();
  expect(client.count("GET /v1/trips/{trip_id}/itineraries")).toBeLessThanOrEqual(1);
  // The overview reads the plan once.
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
  await fireEvent.press(await screen.findByRole("button", { name: /Planning/ }));
  expect(await screen.findByRole("header", { name: "Choose a plan" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "See the proposals" }));
  expect(await screen.findByText("Not planned yet")).toBeOnTheScreen();
});

test("a trip card shows the trip's photo from the API, and the illustration when there is none", async () => {
  const photo = makePhoto();
  const client = createFakeClient(
    trips([
      makeTrip({ cover_image: photo }),
      makeTrip({ id: "t2", title: "Prague", cover_image: null }),
    ]),
  );
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("Prague")).toBeOnTheScreen();
  const photos = screen.getAllByTestId("cover-photo");
  expect(photos).toHaveLength(1); // only the trip that has a photo
  expect(photos[0]!.props.source).toEqual({ uri: `https://api.example.org${photo.url}` });
});
