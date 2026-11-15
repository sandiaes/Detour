import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient, offline } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  WIDER_ID,
  makeDestination,
  makeItinerary,
  makeSummary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { monthGrid } from "../components/ds/Calendar";
import { localToday } from "../domain/trips";
import { SEARCH_DEBOUNCE_MS, unavailableReason, validateForm } from "./CreateTripScreen";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

const generation = () => ({
  generation_id: "g",
  distinct: true,
  jaccard_permille: 400,
  max_jaccard_permille: 600,
  notes: [],
  itineraries: [makeItinerary("essentials"), makeItinerary("wider")],
});

function server(over: Record<string, (c: never) => unknown> = {}) {
  const stored: unknown[] = [];
  return createFakeClient({
    "GET /v1/trips": () => stored,
    "GET /v1/destinations/search": () => ({
      query: "vie",
      external: { state: "not_requested", results: [] },
      results: [
        makeDestination(),
        makeDestination({ ref: "a1", name: "Vienna Woods", kind: "area" }),
        makeDestination({
          ref: "c2",
          name: "Vienne",
          country_name: "France",
          planning_available: false,
          unavailable_reason: "region_not_available",
        }),
        makeDestination({
          ref: "a2",
          name: "Viena Prefecture",
          kind: "area",
          country_name: "Japan",
          unavailable_reason: "area_single_city_only",
        }),
      ],
    }),
    "POST /v1/trips": () => {
      stored.unshift(makeTrip());
      return makeTrip();
    },
    "POST /v1/trips/{trip_id}/itineraries/generate": generation,
    "GET /v1/trips/{trip_id}/itineraries": () => [makeSummary("essentials"), makeSummary("wider")],
    ...over,
  } as never);
}

async function openForm(client = server()) {
  await render(
    <Harness client={client} initial={{ name: "createTrip" }}>
      <AppContent />
    </Harness>,
  );
  return client;
}

async function typeDestination(text: string) {
  await fireEvent.changeText(screen.getByLabelText("Destination"), text);
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10);
  });
}

test("typing a destination searches once, after a pause, and lists the matches", async () => {
  const client = await openForm();
  await fireEvent.changeText(screen.getByLabelText("Destination"), "V");
  expect(screen.getByText("Type at least 2 letters.")).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vi");
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  expect(client.count("GET /v1/destinations/search")).toBe(0); // still waiting for a pause
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10);
  });
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(client.count("GET /v1/destinations/search")).toBe(1);
  expect(client.calls.at(-1)?.params).toMatchObject({ q: "Vie" });
});

test("a repeated query is answered from memory", async () => {
  const client = await openForm();
  await typeDestination("Vie");
  await screen.findByText("Vienna");
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vien");
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(client.count("GET /v1/destinations/search")).toBe(1);
});

test("every result can be chosen; those with no sight data say so and offer only an empty trip", async () => {
  await openForm();
  await typeDestination("Vie");
  await screen.findByText("Vienna");
  const area = screen.getByRole("button", { name: /Vienna Woods/ });
  expect(area.props.accessibilityState?.disabled).toBeFalsy();
  const japan = screen.getByRole("button", { name: /Viena Prefecture/ });
  expect(japan.props.accessibilityState?.disabled).toBeFalsy();
  expect(screen.getByText(/Areas in Japan cannot be planned yet/)).toBeOnTheScreen();
  expect(screen.getAllByText(/No sight data for this region yet/).length).toBeGreaterThan(0);

  // An imported place with no available region is an empty trip (ADR 027).
  await fireEvent.press(screen.getByRole("button", { name: /^Vienne/ }));
  expect(screen.getByTestId("not-plannable")).toBeOnTheScreen();
  expect(
    screen.getByRole("button", { name: "Generate itineraries" }).props.accessibilityState,
  ).toMatchObject({ disabled: true });
  expect(screen.queryByTestId("add-city")).toBeNull();
});

test("a place with no sight data becomes an empty place trip with a gazetteer reference", async () => {
  const client = await openForm();
  await typeDestination("Vie");
  await fireEvent.press(await screen.findByRole("button", { name: /^Vienne/ }));
  await fireEvent.press(screen.getByTestId("empty-trip"));
  await screen.findByText("Overview", {}, { timeout: 3000 }).catch(() => null);
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect(create?.body).toEqual({
    title: "Vienne",
    destination_kind: "place",
    destination_ref: "geonames:c2",
    destination_name: "Vienne",
    destination_lat: 48.2082,
    destination_lon: 16.3738,
    destination_country: "AT",
    duration_days: 3,
    start_date: null,
  });
  expect(client.calls.some((c) => c.path.endsWith("/itineraries/generate"))).toBe(false);
});

test("Search more widely finds any place through Photon and starts an empty place trip", async () => {
  const client = await openForm(
    server({
      "GET /v1/destinations/search": (c: { params: Record<string, unknown> }) => ({
        query: "hall",
        results: [],
        external: c.params.include_external
          ? {
              state: "ok",
              provider: "photon",
              results: [
                {
                  provider: "photon",
                  ref: "N42",
                  name: "Hallstatt",
                  lat: 47.5622,
                  lon: 13.6493,
                  osm_key: "place",
                  osm_value: "village",
                  country_code: "AT",
                  country: "Austria",
                  state: "Upper Austria",
                  city: null,
                  street: null,
                  housenumber: null,
                  postcode: null,
                  licence: "ODbL-1.0",
                },
              ],
            }
          : { state: "not_requested", results: [] },
      }),
    }),
  );
  await typeDestination("Hall");
  expect(await screen.findByText(/Nothing in the imported data matches “Hall”/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("search-wider"));
  await fireEvent.press(await screen.findByTestId("destination-result-photon:N42"));
  // No photo choice for a place with no gazetteer entry: the illustration stays (ADR 027).
  expect(screen.queryByTestId("change-photo")).toBeNull();
  await fireEvent.press(screen.getByTestId("empty-trip"));
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect(create?.body).toMatchObject({
    destination_kind: "place",
    destination_ref: "photon:N42",
    destination_name: "Hallstatt",
    destination_country: "AT",
  });
});

test("when the wider search is not available, the place can be entered by hand with its coordinates", async () => {
  const client = await openForm(
    server({
      "GET /v1/destinations/search": () => ({
        query: "x",
        results: [],
        external: { state: "budget_exhausted", provider: "photon", results: [] },
      }),
    }),
  );
  await typeDestination("Mein Ort");
  await fireEvent.press(await screen.findByTestId("search-wider"));
  expect(await screen.findByText(/The wider search is not available right now/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("enter-by-hand"));
  expect(screen.getByText("Mein Ort")).toBeOnTheScreen();
  // Nothing is created until both coordinates are valid.
  expect(screen.getByTestId("empty-trip").props.accessibilityState).toMatchObject({
    disabled: true,
  });
  await fireEvent.changeText(screen.getByTestId("manual-lat"), "47,5");
  await fireEvent.changeText(screen.getByTestId("manual-lon"), "13.6");
  await fireEvent.press(screen.getByTestId("empty-trip"));
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect(create?.body).toMatchObject({
    destination_kind: "place",
    destination_ref: "manual",
    destination_name: "Mein Ort",
    destination_lat: 47.5,
    destination_lon: 13.6,
  });
});

test("no match is explained, and searching more widely is offered", async () => {
  await openForm(
    server({
      "GET /v1/destinations/search": () => ({
        query: "x",
        results: [],
        external: { state: "not_requested", results: [] },
      }),
    }),
  );
  await typeDestination("Zzz");
  expect(await screen.findByText(/Nothing in the imported data matches “Zzz”/)).toBeOnTheScreen();
  expect(screen.getByTestId("search-wider")).toBeOnTheScreen();
});

test("searching offline says it needs a connection", async () => {
  await openForm(server({ "GET /v1/destinations/search": offline }));
  await typeDestination("Vie");
  expect(await screen.findByText(/Searching needs a connection/)).toBeOnTheScreen();
});

/** "YYYY-MM" of the month after today's, as the calendar shows after one press of Next. */
function nextMonth(): string {
  const [y, m] = localToday().split("-").map(Number) as [number, number];
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, "0")}`;
}

test("Generate itineraries stays unavailable until a destination is chosen", async () => {
  await openForm();
  const button = screen.getByRole("button", { name: "Generate itineraries" });
  expect(button.props.accessibilityState).toMatchObject({ disabled: true });
});

test("the whole flow: search, choose, set details, plan, land on the two proposals", async () => {
  const client = await openForm();
  await typeDestination("Vie");
  await fireEvent.press(await screen.findByRole("button", { name: /^Vienna, Vienna, Austria/ }));
  expect(screen.getByLabelText("Clear destination")).toBeOnTheScreen();

  await fireEvent.press(screen.getByLabelText("More days"));
  // The start date is chosen on a calendar, never typed.
  await fireEvent.press(screen.getByRole("button", { name: "Start date, not set" }));
  expect(screen.getByTestId("cal-month")).toBeOnTheScreen();
  await fireEvent.press(screen.getByLabelText("Next month"));
  await fireEvent.press(screen.getByTestId(`cal-${nextMonth()}-15`));
  expect(screen.getByRole("button", { name: /^Start date, .* 15 / })).toBeOnTheScreen();
  // No currency and no meal budget: budgets are not part of the app (ADR 017).
  expect(screen.queryByLabelText("Currency (optional)")).toBeNull();
  expect(screen.queryByLabelText("Meal budget per person (optional)")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Generate itineraries" }));

  expect(await screen.findByRole("header", { name: "Choose your itinerary" })).toBeOnTheScreen();
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect(create?.body).toEqual({
    title: "Vienna",
    destination_kind: "city",
    destination_ref: "900101",
    duration_days: 4,
    start_date: `${nextMonth()}-15`,
  });
  expect(client.count("POST /v1/trips/{trip_id}/itineraries/generate")).toBe(1);
  // The generated plans were stored, so opening the proposals made no extra plan requests.
  expect(client.count("GET /v1/trips/{trip_id}/itineraries")).toBe(0);
});

test("an empty trip is created without proposals and opens on its own plan", async () => {
  const manual = makeItinerary("essentials", { profile: "manual" } as never);
  const trip = makeTrip({ selected_itinerary_id: manual.id });
  const client = await openForm(
    server({
      "POST /v1/trips/{trip_id}/itineraries": () => manual,
      "PATCH /v1/trips/{trip_id}": () => trip,
      "GET /v1/trips": () => [trip],
    }),
  );
  await typeDestination("Vie");
  await fireEvent.press(await screen.findByRole("button", { name: /^Vienna, Vienna, Austria/ }));
  await fireEvent.press(screen.getByRole("button", { name: "Start a fresh trip" }));

  expect(await screen.findByTestId("day-row-1")).toBeOnTheScreen();
  // No proposals were asked for, and the trip is named after its destination alone.
  expect(client.count("POST /v1/trips/{trip_id}/itineraries/generate")).toBe(0);
  expect(client.count("POST /v1/trips/{trip_id}/itineraries")).toBe(1);
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect((create?.body as { title: string }).title).toBe("Vienna");
  const select = client.calls.find((c) => c.method === "PATCH");
  expect(select?.body).toEqual({ selected_itinerary_id: manual.id });
});

test("public transport is shown but marked as not used yet, and there is no travel style", async () => {
  const client = await openForm();
  expect(screen.queryByRole("radio", { name: "Balanced" })).toBeNull();
  expect(screen.getByText(/saved for later/)).toBeOnTheScreen();
  // Not part of the trip sent to the server.
  expect(client.count("POST /v1/trips")).toBe(0);
});

test("the start date can be cleared again from the calendar", async () => {
  const client = await openForm();
  await typeDestination("Vie");
  await fireEvent.press(await screen.findByRole("button", { name: /^Vienna, Vienna, Austria/ }));
  await fireEvent.press(screen.getByRole("button", { name: "Start date, not set" }));
  expect(screen.queryByTestId("cal-clear")).toBeNull();
  await fireEvent.press(screen.getByTestId(`cal-${localToday().slice(0, 8)}15`));
  await fireEvent.press(screen.getByRole("button", { name: /^Start date, / }));
  await fireEvent.press(screen.getByTestId("cal-clear"));
  expect(screen.getByRole("button", { name: "Start date, not set" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Generate itineraries" }));
  await screen.findByRole("header", { name: "Choose your itinerary" });
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect(create?.body).toMatchObject({ start_date: null });
});

test("the calendar's month grid starts on Monday and has every day once", () => {
  const weeks = monthGrid(2027, 1); // February 2027 starts on a Monday
  expect(weeks[0]?.[0]).toBe("2027-02-01");
  expect(weeks.every((w) => w.length === 7)).toBe(true);
  expect(weeks.flat().filter(Boolean)).toHaveLength(28);
  const may = monthGrid(2027, 4); // May 2027 starts on a Saturday
  expect(may[0]?.slice(0, 5)).toEqual([null, null, null, null, null]);
  expect(may[0]?.[5]).toBe("2027-05-01");
});

test("an area is planned like a city, with its own explanation", async () => {
  const client = await openForm();
  await typeDestination("Vie");
  await fireEvent.press(await screen.findByRole("button", { name: /^Vienna Woods/ }));
  expect(screen.getByText(/choose base cities in the area/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Generate itineraries" }));
  expect(await screen.findByRole("header", { name: "Choose your itinerary" })).toBeOnTheScreen();
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect(create?.body).toMatchObject({ destination_kind: "area", destination_ref: "a1" });
});

test("when planning fails the trip is kept, the reason is shown, and Try again plans without creating a second trip", async () => {
  let calls = 0;
  const client = await openForm(
    server({
      "POST /v1/trips/{trip_id}/itineraries/generate": () =>
        ++calls === 1
          ? {
              status: 422,
              body: {
                detail: "no plan",
                code: "planning_impossible",
                issues: [{ code: "TOO_FEW", text: "Only 2 places are known here." }],
              },
            }
          : generation(),
    }),
  );
  await typeDestination("Vie");
  await fireEvent.press(await screen.findByRole("button", { name: /^Vienna, Vienna, Austria/ }));
  await fireEvent.press(screen.getByRole("button", { name: "Generate itineraries" }));
  expect(await screen.findByText(/does not have enough places/)).toBeOnTheScreen();
  expect(screen.getByText(/Only 2 places are known here/)).toBeOnTheScreen();
  expect(screen.getByText(/The trip was saved/)).toBeOnTheScreen();

  await fireEvent.press(screen.getByRole("button", { name: "Try planning again" }));
  expect(await screen.findByRole("header", { name: "Choose your itinerary" })).toBeOnTheScreen();
  expect(client.count("POST /v1/trips")).toBe(1);
  expect(client.count("POST /v1/trips/{trip_id}/itineraries/generate")).toBe(2);
});

test("offline, planning is disabled and the form says why", async () => {
  await render(
    <Harness state={{ phase: "error", message: "x" }} initial={{ name: "createTrip" }}>
      <AppContent />
    </Harness>,
  );
  expect(screen.getByText(/Planning a trip needs a connection/)).toBeOnTheScreen();
});

test("form helpers", () => {
  expect(validateForm({ startDate: "" })).toEqual({});
  expect(validateForm({ startDate: "2027-13-01" })).toEqual({ date: expect.any(String) });
  expect(unavailableReason(makeDestination({ kind: "area" }))).toBeNull();
  expect(
    unavailableReason(
      makeDestination({ kind: "area", unavailable_reason: "area_single_city_only" }),
    ),
  ).toMatch(/Japan/);
  expect([ESSENTIALS_ID, WIDER_ID, TRIP_ID]).toHaveLength(3);
});
