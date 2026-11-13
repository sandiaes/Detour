import type {
  GenerationResult,
  Itinerary,
  ItinerarySummary,
  Trip,
  TripCreate,
} from "@detour/shared";
import { useCallback } from "react";

import { useBackend } from "../api/BackendProvider";
import { NetworkError, call, callEmpty } from "../api/unwrap";
import { useData } from "./DataProvider";

// Everything the app changes on the server. There is no offline editing: with no connection these
// throw NetworkError and the screen says so (scope guard: no offline editing or sync).

export const keys = {
  trips: "trips",
  itineraries: (tripId: string) => `itineraries:${tripId}`,
  itinerary: (id: string) => `itinerary:${id}`,
};

function toSummary(itinerary: Itinerary): ItinerarySummary {
  const { days: _days, ...summary } = itinerary;
  return summary;
}

export function useTripActions() {
  const { state } = useBackend();
  const data = useData();
  const client = state.phase === "ready" ? state.connection.client : null;

  const need = useCallback(() => {
    if (!client) throw new NetworkError("The server is not connected yet.");
    return client;
  }, [client]);

  const createTrip = useCallback(
    async (body: TripCreate): Promise<Trip> => {
      const trip = await call(need().POST("/v1/trips", { body }));
      // If the list is held, it now includes the trip, so the next screen needs no request. If it
      // is not held, that screen fetches it and the server's list has the trip.
      data.update<Trip[]>(keys.trips, (list) => [trip, ...list]);
      return trip;
    },
    [need, data],
  );

  /** Plans the trip. The two itineraries come back whole, so they are stored: opening one makes
   * no further request. */
  const generate = useCallback(
    async (tripId: string): Promise<GenerationResult> => {
      const result = await call(
        need().POST("/v1/trips/{trip_id}/itineraries/generate", {
          params: { path: { trip_id: tripId } },
        }),
      );
      data.invalidate(keys.itineraries(tripId));
      data.put(keys.itineraries(tripId), result.itineraries.map(toSummary));
      for (const itinerary of result.itineraries) data.put(keys.itinerary(itinerary.id), itinerary);
      return result;
    },
    [need, data],
  );

  const selectPlan = useCallback(
    async (tripId: string, itineraryId: string): Promise<Trip> => {
      const trip = await call(
        need().PATCH("/v1/trips/{trip_id}", {
          params: { path: { trip_id: tripId } },
          body: { selected_itinerary_id: itineraryId },
        }),
      );
      data.update<Trip[]>(keys.trips, (list) => list.map((t) => (t.id === trip.id ? trip : t)));
      const mark = <T extends { id: string; status: string }>(item: T): T => ({
        ...item,
        status:
          item.id === itineraryId
            ? "selected"
            : item.status === "selected"
              ? "proposed"
              : item.status,
      });
      data.update<ItinerarySummary[]>(keys.itineraries(tripId), (list) => list.map(mark));
      data.update<Itinerary>(keys.itinerary(itineraryId), mark);
      return trip;
    },
    [need, data],
  );

  /** Deletes the trip with its plans on the server, then forgets everything held for it. */
  const deleteTrip = useCallback(
    async (trip: Trip): Promise<void> => {
      await callEmpty(
        need().DELETE("/v1/trips/{trip_id}", { params: { path: { trip_id: trip.id } } }),
      );
      data.update<Trip[]>(keys.trips, (list) => list.filter((t) => t.id !== trip.id));
      data.forget(keys.itineraries(trip.id));
      if (trip.selected_itinerary_id) data.forget(keys.itinerary(trip.selected_itinerary_id));
    },
    [need, data],
  );

  return { createTrip, generate, selectPlan, deleteTrip, connected: client !== null };
}
