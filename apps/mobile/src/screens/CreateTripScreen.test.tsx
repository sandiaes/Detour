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

test("areas can be chosen; Japanese areas and regions without data cannot, and the row says why", async () => {
  await openForm();
  await typeDestination("Vie");
  await screen.findByText("Vienna");
  const area = screen.getByRole("button", { name: /Vienna Woods/ });
  expect(area.props.accessibilityState).toMatchObject({ disabled: false });
  const japan = screen.getByRole("button", { name: /Viena Prefecture/ });
  expect(japan.props.accessibilityState).toMatchObject({ disabled: true });
  expect(screen.getByText(/Areas in Japan cannot be planned yet/)).toBeOnTheScreen();
  const unavailable = screen.getByRole("button", { name: /Vienne/ });
  expect(unavailable.props.accessibilityState).toMatchObject({ disabled: true });
  expect(screen.getByText(/this region's data has not been imported/)).toBeOnTheScreen();
});

test("no match is explained", async () => {
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
  expect(await screen.findByText(/No place matches “Zzz”/)).toBeOnTheScreen();
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

test("Suggest itineraries stays unavailable until a destination is chosen", async () => {
  await openForm();
  const button = screen.getByRole("button", { name: "Suggest itineraries" });
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
  await fireEvent.press(screen.getByRole("button", { name: "Suggest itineraries" }));

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
  await fireEvent.press(screen.getByRole("button", { name: "Start with an empty trip" }));

  expect(await screen.findByRole("header", { name: "Your itineraries" })).toBeOnTheScreen();
  expect(screen.getByText("Your own plan")).toBeOnTheScreen();
  // No proposals were asked for, and the trip is named after its destination alone.
  expect(client.count("POST /v1/trips/{trip_id}/itineraries/generate")).toBe(0);
  expect(client.count("POST /v1/trips/{trip_id}/itineraries")).toBe(1);
  const create = client.calls.find((c) => c.method === "POST" && c.path === "/v1/trips");
  expect((create?.body as { title: string }).title).toBe("Vienna");
  const select = client.calls.find((c) => c.method === "PATCH");
  expect(select?.body).toEqual({ selected_itinerary_id: manual.id });
});

test("travel style and public transport are chosen but marked as not used yet", async () => {
  const client = await openForm();
  expect(screen.getByRole("radio", { name: "Balanced" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
  await fireEvent.press(screen.getByRole("radio", { name: "Relaxed" }));
  expect(screen.getByRole("radio", { name: "Relaxed" }).props.accessibilityState).toMatchObject({
    selected: true,
  });
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
  await fireEvent.press(screen.getByRole("button", { name: "Suggest itineraries" }));
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
  await fireEvent.press(screen.getByRole("button", { name: "Suggest itineraries" }));
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
  await fireEvent.press(screen.getByRole("button", { name: "Suggest itineraries" }));
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
