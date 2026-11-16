import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { AppContent } from "../App";
import { canShareWith, personName, sharedLine } from "../domain/sharing";
import { createFakeClient } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

const ME = "11111111-2222-3333-4444-555555555555";
const ANA = "22222222-2222-3333-4444-555555555555";
const ANA_LINK = { person_id: ANA, name: "Ana", linked_at: "2026-11-16T10:00:00Z" };

function me(over: Record<string, unknown> = {}) {
  return {
    person_id: ME,
    device_id: ME,
    display_name: "Jose",
    people: [ANA_LINK],
    devices: [],
    recovery_code_created_at: null,
    ...over,
  };
}

const OWNER = { person_id: ME, name: "Jose", role: "owner", you: true };
const ANA_EDITOR = { person_id: ANA, name: "Ana", role: "editor", you: false };

function trip(over: Record<string, unknown> = {}) {
  return makeTrip({ selected_itinerary_id: ESSENTIALS_ID, members: [OWNER], ...over } as never);
}

async function open(initial: object, handlers: Record<string, unknown> = {}) {
  const client = createFakeClient({
    "GET /v1/me": () => me(),
    "GET /v1/trips": () => [trip()],
    ...handlers,
  } as never);
  await render(
    <Harness client={client} initial={initial as never}>
      <AppContent />
    </Harness>,
  );
  return client;
}

const settings = { name: "tripSettings", tripId: TRIP_ID };

test("the owner shares a trip with a linked person", async () => {
  const client = await open(settings, {
    "POST /v1/trips/{trip_id}/members": () => trip({ members: [OWNER, ANA_EDITOR] }),
  });
  expect(await screen.findByText(/Only you\. Share it/)).toBeOnTheScreen();
  await fireEvent.press(await screen.findByTestId(`share-${ANA}`));
  expect(await screen.findByText(/Shared with Ana\./)).toBeOnTheScreen();
  expect(client.calls.find((c) => c.path === "/v1/trips/{trip_id}/members")?.body).toEqual({
    person_id: ANA,
  });
  expect(screen.queryByTestId(`share-${ANA}`)).toBeNull();
});

test("the owner stops sharing after confirming", async () => {
  const client = await open(settings, {
    "GET /v1/trips": () => [trip({ members: [OWNER, ANA_EDITOR] })],
    "DELETE /v1/trips/{trip_id}/members/{person_id}": () => undefined,
  });
  await fireEvent.press(await screen.findByTestId(`unshare-${ANA}`));
  await fireEvent.press(await screen.findByTestId("confirm-unshare"));
  await waitFor(() =>
    expect(client.calls.find((c) => c.method === "DELETE")?.params).toEqual({
      trip_id: TRIP_ID,
      person_id: ANA,
    }),
  );
  expect(await screen.findByText(/Only you\. Share it/)).toBeOnTheScreen();
});

test("a member sees who created the trip, can leave it, and cannot delete it", async () => {
  const shared = trip({
    role: "editor",
    members: [
      { person_id: ANA, name: "Ana", role: "owner", you: false },
      { person_id: ME, name: "Jose", role: "editor", you: true },
    ],
  });
  const client = await open(settings, {
    "GET /v1/trips": () => [shared],
    "DELETE /v1/trips/{trip_id}/members/{person_id}": () => undefined,
  });
  expect(await screen.findByText(/Ana created this trip and shared it with you/)).toBeOnTheScreen();
  expect(screen.queryByTestId("delete-trip")).toBeNull();
  await fireEvent.press(screen.getByTestId("leave-trip"));
  await fireEvent.press(await screen.findByTestId("confirm-leave"));
  await waitFor(() =>
    expect(client.calls.find((c) => c.method === "DELETE")?.params).toEqual({
      trip_id: TRIP_ID,
      person_id: ME,
    }),
  );
  expect(await screen.findByRole("header", { name: "Detour" })).toBeOnTheScreen();
});

test("a shared trip's card says who else is on it", async () => {
  await open(
    { name: "trips" },
    { "GET /v1/trips": () => [trip({ members: [OWNER, ANA_EDITOR] })] },
  );
  expect(await screen.findByText(/With Ana/)).toBeOnTheScreen();
});

test("People: save a name, show an invite code and link with one", async () => {
  const client = await open(
    { name: "people" },
    {
      "GET /v1/me": () => me({ display_name: null, people: [] }),
      "PATCH /v1/me": () => me({ display_name: "Jose", people: [] }),
      "POST /v1/me/invite-codes": () => ({ code: "K7MQ-R4XT", expires_at: "2026-11-16T10:10:00Z" }),
      "POST /v1/people/link": () => me(),
    },
  );
  expect(await screen.findByText("Nobody yet.")).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByTestId("people-name"), "Jose");
  await fireEvent.press(screen.getByTestId("people-save-name"));
  await waitFor(() => expect(client.calls.some((c) => c.method === "PATCH")).toBe(true));
  expect(await screen.findByText(/Others now see you as Jose/)).toBeOnTheScreen();
  expect(client.calls.find((c) => c.method === "PATCH")?.body).toEqual({ display_name: "Jose" });

  await fireEvent.press(screen.getByTestId("people-show-invite"));
  expect(await screen.findByTestId("invite-code")).toHaveTextContent("K7MQ-R4XT");

  await fireEvent.changeText(screen.getByTestId("people-code-input"), "abcd-efgh");
  await fireEvent.press(screen.getByTestId("people-link"));
  expect(await screen.findByText(/You are linked with Ana/)).toBeOnTheScreen();
  expect(await screen.findByText("Ana")).toBeOnTheScreen();
});

test("helpers", () => {
  const t = trip({ members: [OWNER, ANA_EDITOR] });
  expect(sharedLine(t)).toBe("With Ana");
  expect(sharedLine(trip())).toBeNull();
  expect(canShareWith(t, [ANA_LINK])).toEqual([]);
  expect(canShareWith(trip(), [ANA_LINK])).toEqual([ANA_LINK]);
  expect(personName(null)).toBe("Someone without a name");
});
