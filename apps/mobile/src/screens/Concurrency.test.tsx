import { act, render, renderHook, screen } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { AppContent } from "../App";
import { ApiError } from "../api/unwrap";
import { keys } from "../data/actions";
import { ifMatch, useChangeActions } from "../data/changes";
import { useData } from "../data/DataProvider";
import { changedByLine } from "../domain/sharing";
import { createFakeClient } from "../testing/fakeClient";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeSummary, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

const ME = { person_id: "me", name: "Jose", role: "owner", you: true };
const ANA = { person_id: "ana", name: "Ana", role: "editor", you: false };

function sharedTrip() {
  return makeTrip({ selected_itinerary_id: ESSENTIALS_ID, members: [ME, ANA] } as never);
}

function planChangedBy(you: boolean) {
  return makeItinerary("essentials", {
    status: "selected",
    version: 7,
    last_change: {
      person_id: you ? "me" : "ana",
      name: you ? "Jose" : "Ana",
      you,
      at: "2026-11-16T09:55:00Z",
    },
  } as never);
}

test("a plan change sends the version this phone last read, and a refusal reads the plan again", async () => {
  const client = createFakeClient({
    "DELETE /v1/items/{item_id}": () => ({
      status: 409,
      body: { detail: "x", code: "plan_changed", current_version: 8 },
    }),
  } as never);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <Harness client={client}>{children}</Harness>
  );
  const { result } = await renderHook(() => ({ actions: useChangeActions(), data: useData() }), {
    wrapper,
  });
  await act(async () => {
    result.current.data.put(keys.itinerary(ESSENTIALS_ID), planChangedBy(true));
  });
  let error: unknown;
  await act(async () => {
    await result.current.actions
      .removeItem(TRIP_ID, ESSENTIALS_ID, "item-1")
      .catch((e: unknown) => (error = e));
  });
  expect(client.calls[0]?.header).toEqual({ "If-Match": '"7"' });
  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe("plan_changed");
  // The stale copy is gone, so the next screen reads the plan again.
  expect(result.current.data.memory.has(keys.itinerary(ESSENTIALS_ID))).toBe(false);
});

test("a shared trip's overview says who changed the plan last", async () => {
  const client = createFakeClient({
    "GET /v1/trips": () => [sharedTrip()],
    "GET /v1/itineraries/{itinerary_id}": () => planChangedBy(false),
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: "selected" }),
    ],
    "GET /v1/trips/{trip_id}/stays": () => [],
    "GET /v1/itineraries/{itinerary_id}/versions": () => [],
  } as never);
  await render(
    <Harness client={client} initial={{ name: "tripOverview", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  expect(await screen.findByText(/Changed by Ana/)).toBeOnTheScreen();
});

test("helpers", () => {
  expect(ifMatch(3)).toEqual({ "If-Match": '"3"' });
  expect(ifMatch(undefined)).toBeUndefined();
  const now = Date.parse("2026-11-16T10:00:00Z");
  expect(changedByLine(sharedTrip(), planChangedBy(false), now)).toBe(
    "Changed by Ana 5 minutes ago",
  );
  expect(changedByLine(sharedTrip(), planChangedBy(true), now)).toBeNull();
  const solo = makeTrip({ members: [ME] } as never);
  expect(changedByLine(solo, planChangedBy(false), now)).toBeNull();
});
