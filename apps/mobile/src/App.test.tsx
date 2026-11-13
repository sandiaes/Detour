import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "./App";
import { createMemoryStore } from "./cache/store";
import { SEARCH_DEBOUNCE_MS } from "./screens/CreateTripScreen";
import { createFakeClient } from "./testing/fakeClient";
import {
  ESSENTIALS_ID,
  makeDestination,
  makeItinerary,
  makeSummary,
  makeTrip,
} from "./testing/fixtures";
import { Harness } from "./testing/harness";

// Timers are restored after the screens unmount (Testing Library cleans up first).
afterEach(() => jest.useRealTimers());

test("Trips and Settings are the two tabs, and Settings shows the connection and credits", async () => {
  const client = createFakeClient({
    "GET /v1/trips": () => [],
    "GET /v1/attributions": () => [
      {
        name: "OpenStreetMap",
        text: "© OpenStreetMap contributors",
        url: "https://www.openstreetmap.org/copyright",
        licence: "ODbL-1.0",
        applies_to: "Places",
      },
      {
        name: "GeoNames",
        text: "GeoNames",
        url: "https://www.geonames.org",
        licence: "CC-BY-4.0",
        applies_to: "Cities",
      },
    ],
  });
  await render(
    <Harness client={client}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByRole("header", { name: "Trips" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("tab", { name: "Settings" }));
  expect(await screen.findByRole("header", { name: "Settings" })).toBeOnTheScreen();
  expect(screen.getByText("Status: connected")).toBeOnTheScreen();
  expect(screen.getByText(/detour-api 0\.1\.0 \(abcdef1\)/)).toBeOnTheScreen();
  expect(await screen.findByText("© OpenStreetMap contributors")).toBeOnTheScreen();
  expect(screen.getByText("GeoNames")).toBeOnTheScreen();
  expect(screen.getByText("Places · ODbL-1.0")).toBeOnTheScreen();
});

test("the tab bar is hidden on pushed screens so back is the only way out", async () => {
  await render(
    <Harness client={createFakeClient({ "GET /v1/trips": () => [] })}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText("No trips yet");
  expect(screen.getByRole("tab", { name: "Trips" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "New trip" }));
  expect(screen.queryByRole("tab", { name: "Trips" })).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("tab", { name: "Trips" })).toBeOnTheScreen();
});

test("the banner says the server is waking up during a cold start", async () => {
  await render(
    <Harness state={{ phase: "connecting", waking: true }}>
      <AppContent />
    </Harness>,
  );
  expect(screen.getByText(/Waking the server\. The free host was asleep/)).toBeOnTheScreen();
});

test("a failed connection shows the reason and a retry button", async () => {
  const retry = jest.fn();
  await render(
    <Harness state={{ phase: "error", message: "Health check failed (HTTP 503)." }} retry={retry}>
      <AppContent />
    </Harness>,
  );
  expect(screen.getByText(/Health check failed \(HTTP 503\)/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Retry"));
  expect(retry).toHaveBeenCalledTimes(1);
});

test("a new installation does not show another installation's saved trips", async () => {
  const cache = createMemoryStore();
  await cache.set("meta:installation", "some-other-installation");
  await cache.set("trips", [makeTrip({ title: "Someone else's trip" })]);
  const client = createFakeClient({ "GET /v1/trips": () => [] });
  await render(
    <Harness client={client} cache={cache}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText("No trips yet")).toBeOnTheScreen();
  expect(screen.queryByText("Someone else's trip")).toBeNull();
  expect((await cache.get("meta:installation"))?.value).toBe(
    "11111111-2222-3333-4444-555555555555",
  );
});

// The critical path of the product, through the real screens with a fake server.
test("create a trip, compare the proposals, select one, read its days, see it on the map", async () => {
  jest.useFakeTimers();
  {
    const stored: unknown[] = [];
    let selected: string | null = null;
    const generated = {
      generation_id: "g",
      distinct: true,
      jaccard_permille: 400,
      max_jaccard_permille: 600,
      notes: [],
      itineraries: [makeItinerary("essentials"), makeItinerary("wider")],
    };
    const client = createFakeClient({
      "GET /v1/trips": () => stored,
      "GET /v1/destinations/search": () => ({
        query: "Vie",
        results: [makeDestination()],
        external: { state: "not_requested", results: [] },
      }),
      "POST /v1/trips": () => {
        stored.unshift(makeTrip());
        return makeTrip();
      },
      "POST /v1/trips/{trip_id}/itineraries/generate": () => generated,
      "GET /v1/trips/{trip_id}/itineraries": () => [
        makeSummary("essentials"),
        makeSummary("wider"),
      ],
      "PATCH /v1/trips/{trip_id}": ({ body }: never) => {
        selected = (body as { selected_itinerary_id: string }).selected_itinerary_id;
        stored[0] = makeTrip({ selected_itinerary_id: selected });
        return stored[0];
      },
    } as never);
    await render(
      <Harness client={client}>
        <AppContent />
      </Harness>,
    );

    await fireEvent.press(await screen.findByText("Plan a trip"));
    await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
    await act(async () => void jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10));
    await fireEvent.press(await screen.findByRole("button", { name: /^Vienna, Vienna, Austria/ }));
    await fireEvent.press(screen.getByRole("button", { name: "Plan trip" }));

    expect(await screen.findByText("How they differ")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Select the Essentials plan" }));
    expect(await screen.findByText("✓ Selected")).toBeOnTheScreen();
    expect(selected).toBe(ESSENTIALS_ID);

    await fireEvent.press(
      screen.getByRole("button", { name: "View the days of the Essentials plan" }),
    );
    expect(await screen.findByText("Schönbrunn Palace")).toBeOnTheScreen();
    expect(screen.getByText("Estimated")).toBeOnTheScreen();

    await fireEvent.press(screen.getByRole("button", { name: "Show the map" }));
    expect(await screen.findByTestId("map")).toBeOnTheScreen();
    expect(screen.getByText("Data from OpenStreetMap")).toBeOnTheScreen();

    // Back to the list of trips: the selected plan is shown there without refetching the list.
    await fireEvent.press(screen.getByRole("button", { name: "Back" }));
    await fireEvent.press(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("header", { name: "Trips" })).toBeOnTheScreen();
    expect(screen.getByText("✓ Plan selected")).toBeOnTheScreen();
    expect(client.count("GET /v1/trips")).toBe(1);
  }
});
