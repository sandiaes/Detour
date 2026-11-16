import type { Day, Itinerary } from "@detour/shared";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { AppContent } from "../App";
import { AddToTripSheet } from "../nav/BottomNav";
import { createFakeClient } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeLeg, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

jest.setTimeout(30_000);

// Transport legs the user enters by hand (ADR 032): adding one, a length left unknown, an
// arrival time instead of a length, a typed end, changing and removing one, and how the day list
// shows it. The server's answers are faked.

type Body = Record<string, unknown>;

function planWith(extra: (days: Day[]) => void = () => {}): Itinerary {
  const plan = makeItinerary("essentials", { status: "selected" });
  extra(plan.days);
  return plan;
}

async function showForm(
  route: { day?: number; itemId?: string } = {},
  plan: Itinerary = planWith(),
  handlers: Record<string, unknown> = {},
) {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": () => plan,
    "GET /v1/trips/{trip_id}/stays": () => [],
    ...handlers,
  } as never);
  await render(
    <Harness
      client={client}
      initial={{ name: "transportLeg", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, ...route }}
    >
      <AppContent />
    </Harness>,
  );
  await screen.findByText("Add transport", {}, { timeout: 5000 }).catch(() => undefined);
  return client;
}

test("a train between two stops is added as the user entered it", async () => {
  const bodies: Body[] = [];
  await showForm({ day: 1 }, planWith(), {
    "POST /v1/itineraries/{itinerary_id}/days/{day_index}/items": ({ body }: { body: Body }) => {
      bodies.push(body);
      return makeLeg();
    },
  });
  await fireEvent.press(await screen.findByTestId("leg-mode"));
  await fireEvent.press(screen.getByTestId("leg-mode-train"));
  await fireEvent.press(screen.getByTestId("leg-from"));
  await fireEvent.press(screen.getByText("Belvedere"));
  await fireEvent.press(screen.getByTestId("leg-to"));
  await fireEvent.press(screen.getByText("St. Stephen's Cathedral"));
  await fireEvent.changeText(screen.getByTestId("leg-start"), "10:12");
  await fireEvent.changeText(screen.getByTestId("leg-length"), "1h30");
  await fireEvent.changeText(screen.getByTestId("leg-note"), "Coach 7");
  expect(screen.getByTestId("leg-length-said")).toHaveTextContent("Length: 1 h 30 min");
  await fireEvent.press(screen.getByTestId("leg-save"));
  await waitFor(() => expect(bodies).toHaveLength(1));
  expect(bodies[0]).toMatchObject({
    type: "transport",
    start_time: "10:12:00",
    duration_minutes: 90,
    transport: {
      mode: "train",
      from_name: "Belvedere",
      to_name: "St. Stephen's Cathedral",
      is_journey: false,
      note: "Coach 7",
    },
  });
  expect((bodies[0]!.transport as Body).from_lat).toBe(48.1916);
});

test("a length left out is sent as unknown, and an end can be typed by hand", async () => {
  const bodies: Body[] = [];
  await showForm({ day: 1 }, planWith(), {
    "POST /v1/itineraries/{itinerary_id}/days/{day_index}/items": ({ body }: { body: Body }) => {
      bodies.push(body);
      return makeLeg();
    },
  });
  await fireEvent.press(await screen.findByTestId("leg-from"));
  await fireEvent.press(screen.getByTestId("leg-from-type"));
  await fireEvent.changeText(screen.getByTestId("leg-from-name"), "Wien Hbf");
  await fireEvent.press(screen.getByTestId("leg-from-use"));
  await fireEvent.press(screen.getByTestId("leg-to"));
  await fireEvent.press(screen.getByTestId("leg-to-type"));
  await fireEvent.changeText(screen.getByTestId("leg-to-name"), "Graz Hbf");
  await fireEvent.press(screen.getByTestId("leg-to-use"));
  expect(screen.getByTestId("leg-length-said")).toHaveTextContent(/time not entered/);
  await fireEvent.press(screen.getByTestId("leg-save"));
  await waitFor(() => expect(bodies).toHaveLength(1));
  expect(bodies[0]).toMatchObject({
    start_time: null,
    duration_minutes: null,
    transport: { from_name: "Wien Hbf", from_lat: null, to_name: "Graz Hbf", to_lat: null },
  });
});

test("an arrival time gives the length, and one before the start is the next day", async () => {
  await showForm({ day: 1 });
  await fireEvent.changeText(await screen.findByTestId("leg-start"), "22:30");
  await fireEvent.press(screen.getByTestId("leg-length-by-arrival"));
  await fireEvent.changeText(screen.getByTestId("leg-arrival"), "07:10");
  expect(screen.getByTestId("leg-length-said")).toHaveTextContent("Length: 8 h 40 min");
});

test("the save button waits for both ends", async () => {
  await showForm({ day: 1 });
  expect(await screen.findByTestId("leg-save")).toBeDisabled();
});

test("a leg is changed, and removed after a confirmation", async () => {
  const patches: Body[] = [];
  const deleted: string[] = [];
  const plan = planWith((days) => {
    days[0]!.items.splice(2, 0, makeLeg({ id: "leg1", day_id: days[0]!.id }));
  });
  await showForm({ itemId: "leg1" }, plan, {
    "PATCH /v1/items/{item_id}": ({ body }: { body: Body }) => {
      patches.push(body);
      return makeLeg();
    },
    "DELETE /v1/items/{item_id}": ({ params }: { params: { item_id: string } }) => {
      deleted.push(params.item_id);
      return undefined;
    },
  });
  expect(await screen.findByText("Change transport")).toBeTruthy();
  await fireEvent.press(screen.getByTestId("leg-mode"));
  await fireEvent.press(screen.getByTestId("leg-mode-bus"));
  await fireEvent.press(screen.getByTestId("leg-length-unknown"));
  await fireEvent.press(screen.getByTestId("leg-save"));
  await waitFor(() => expect(patches).toHaveLength(1));
  expect(patches[0]).toMatchObject({
    duration_minutes: null,
    start_time: "10:12:00",
    transport: { mode: "bus", from_name: "Rome", to_name: "Florence" },
  });
  expect(patches[0]).not.toHaveProperty("day_index");
});

test("removing asks first", async () => {
  const deleted: string[] = [];
  const plan = planWith((days) => {
    days[0]!.items.splice(2, 0, makeLeg({ id: "leg1", day_id: days[0]!.id }));
  });
  await showForm({ itemId: "leg1" }, plan, {
    "DELETE /v1/items/{item_id}": ({ params }: { params: { item_id: string } }) => {
      deleted.push(params.item_id);
      return undefined;
    },
  });
  await fireEvent.press(await screen.findByTestId("leg-remove"));
  expect(deleted).toEqual([]);
  await fireEvent.press(await screen.findByText("Yes, remove it"));
  await waitFor(() => expect(deleted).toEqual(["leg1"]));
});

test("the day list shows a leg with its mode, and a journey leg instead of the computed one", async () => {
  const plan = planWith((days) => {
    days[0]!.items.splice(2, 0, makeLeg({ id: "leg1", day_id: days[0]!.id }));
    const leg = makeLeg(
      { id: "j0", day_id: days[1]!.id, start_time: "08:00:00", end_time: "10:30:00" },
      { is_journey: true, from_name: "Vienna", to_name: "Graz", mode: "bus" },
    );
    days[1]!.items.unshift({ ...leg, duration_minutes: 150 });
    days[1]!.arrival = { ...days[1]!.arrival!, covered_by_item_id: "j0" };
  });
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
  expect(await screen.findByTestId("leg-leg1")).toBeTruthy();
  expect(screen.getByText("Train · 1 h 30 min · 10:12 to 11:42")).toBeTruthy();
  expect(screen.getByLabelText(/^Train from Rome to Florence\./)).toBeTruthy();

  await fireEvent.press(screen.getByRole("tab", { name: "Day 2, Sun 2 May" }));
  expect(await screen.findByTestId("journey-2")).toBeTruthy();
  expect(screen.getByText("Bus from Vienna · 2 h 30 min · 08:00 to 10:30")).toBeTruthy();
  expect(screen.queryByTestId("arrival-2")).toBeNull();
});

test("the Add sheet offers Transport once the trip has a plan", async () => {
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
  } as never);
  await render(
    <Harness client={client} initial={{ name: "trips" }}>
      <AddToTripSheet tripId={TRIP_ID} onClose={() => {}} />
    </Harness>,
  );
  const row = await screen.findByTestId("add-sheet-transport");
  await waitFor(() => expect(row).not.toBeDisabled());
  expect(screen.getByText(/A train, bus or ferry you took or will take/)).toBeTruthy();
});

test("a ticket can be attached to a leg: Add document opens linked to it", async () => {
  const plan = planWith((days) => {
    days[0]!.items.splice(2, 0, makeLeg({ id: "leg1", day_id: days[0]!.id }));
  });
  await showForm({ itemId: "leg1" }, plan);
  await fireEvent.press(await screen.findByTestId("leg-document"));
  expect(await screen.findByRole("header", { name: "Add document" })).toBeOnTheScreen();
});
