import type {
  ChangeSet,
  CoverCandidate,
  GenerationResult,
  Itinerary,
  ItinerarySummary,
  Trip,
  TripCreate,
  TripVisit,
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
  versions: (id: string) => `versions:${id}`,
  visits: (tripId: string) => `visits:${tripId}`,
  archive: (tripId: string) => `archive:${tripId}`,
  stays: (tripId: string) => `stays:${tripId}`,
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

  /** A clean trip: one empty day per trip day, chosen as the trip's plan at once, so the trip opens
   * on it and places can be added freely. No proposals are made. */
  const startEmptyTrip = useCallback(
    async (tripId: string): Promise<Trip> => {
      const itinerary = await call(
        need().POST("/v1/trips/{trip_id}/itineraries", {
          params: { path: { trip_id: tripId } },
        }),
      );
      data.put(keys.itinerary(itinerary.id), itinerary);
      data.put(keys.itineraries(tripId), [toSummary(itinerary)]);
      return selectPlan(tripId, itinerary.id);
    },
    [need, data, selectPlan],
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
      data.forget(keys.visits(trip.id));
      data.forget(keys.archive(trip.id));
    },
    [need, data],
  );

  /** Makes the trip a past trip (ADR 006): the server keeps the visits and deletes the plans, so
   * everything held for the plans is forgotten here too. */
  const archiveTrip = useCallback(
    async (trip: Trip): Promise<Trip> => {
      const past = await call(
        need().POST("/v1/trips/{trip_id}/archive", { params: { path: { trip_id: trip.id } } }),
      );
      data.update<Trip[]>(keys.trips, (list) => list.map((t) => (t.id === past.id ? past : t)));
      data.forget(keys.itineraries(trip.id));
      if (trip.selected_itinerary_id) data.forget(keys.itinerary(trip.selected_itinerary_id));
      data.forget(keys.visits(trip.id));
      data.forget(keys.archive(trip.id));
      return past;
    },
    [need, data],
  );

  /** Confirms or clears one archived visit (the app cannot know what was really visited). */
  const setVisitConfirmed = useCallback(
    async (tripId: string, visitId: string, confirmed: boolean): Promise<TripVisit> => {
      const visit = await call(
        need().PATCH("/v1/trips/{trip_id}/visits/{visit_id}", {
          params: { path: { trip_id: tripId, visit_id: visitId } },
          body: { confirmed },
        }),
      );
      data.update<TripVisit[]>(keys.visits(tripId), (list) =>
        list.map((v) => (v.id === visit.id ? visit : v)),
      );
      data.forget(keys.archive(tripId)); // the count of skipped visits changed
      return visit;
    },
    [need, data],
  );

  /** Photos to choose a cover from (ADR 022 amendment): slow the first time for a destination
   * (the backend asks Wikimedia and makes previews), then cached for a week. */
  const coverCandidates = useCallback(
    async (kind: "city" | "area", ref: string): Promise<CoverCandidate[]> =>
      call(
        need().GET("/v1/destinations/{kind}/{ref}/cover-candidates", {
          params: { path: { kind, ref } },
        }),
      ),
    [need],
  );

  /** Set the trip's cover to a candidate, or back to the automatic photo with null. */
  const setCover = useCallback(
    async (tripId: string, commonsFile: string | null): Promise<Trip> => {
      const trip = await call(
        need().PUT("/v1/trips/{trip_id}/cover", {
          params: { path: { trip_id: tripId } },
          body: { commons_file: commonsFile },
        }),
      );
      data.update<Trip[]>(keys.trips, (list) => list.map((t) => (t.id === trip.id ? trip : t)));
      return trip;
    },
    [need, data],
  );

  /** A multi-city trip with a chosen plan: preview new cities as a change set (ADR 024). */
  const previewStops = useCallback(
    async (tripId: string, stops: { city_id: number; days: number }[]): Promise<ChangeSet> =>
      call(
        need().POST("/v1/trips/{trip_id}/stops/preview", {
          params: { path: { trip_id: tripId } },
          body: { stops },
        }),
      ),
    [need],
  );

  /** A multi-city trip without a chosen plan: its cities are replaced at once. */
  const replaceStops = useCallback(
    async (tripId: string, stops: { city_id: number; days: number }[]): Promise<Trip> => {
      const trip = await call(
        need().PUT("/v1/trips/{trip_id}/stops", {
          params: { path: { trip_id: tripId } },
          body: { stops },
        }),
      );
      data.update<Trip[]>(keys.trips, (list) => list.map((t) => (t.id === trip.id ? trip : t)));
      data.invalidate(keys.itineraries(tripId));
      return trip;
    },
    [need, data],
  );

  return {
    previewStops,
    replaceStops,
    coverCandidates,
    setCover,
    createTrip,
    generate,
    startEmptyTrip,
    selectPlan,
    deleteTrip,
    archiveTrip,
    setVisitConfirmed,
    connected: client !== null,
  };
}
