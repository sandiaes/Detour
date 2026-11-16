import type { ArchiveInfo, Itinerary, Trip } from "@detour/shared";

import { call } from "../api/unwrap";
import {
  type TripCounts,
  archiveOnly,
  countsFromArchive,
  countsFromItinerary,
  countsWithoutPlan,
} from "../domain/trips";
import { keys } from "./actions";
import { type Resource, useResource } from "./DataProvider";

/** The active plan of a trip, read through the shared cache (null key when there is none). */
export function useActivePlan(trip: Trip | undefined): Resource<Itinerary> {
  const id = trip ? trip.selected_itinerary_id : null;
  return useResource<Itinerary>(
    id ? keys.itinerary(id) : null,
    (c) =>
      call(
        c.GET("/v1/itineraries/{itinerary_id}", {
          params: { path: { itinerary_id: id as string } },
        }),
      ),
    { ttlMs: 10 * 60_000 },
  );
}

/**
 * What a trip contains, for its card and overview. Uses the same cached reads as the plan and
 * past-trip screens, so opening the trip afterwards needs no further request. `counts` is null
 * while the figures are loading; figures that cannot be known stay null inside it.
 */
export function useTripCounts(trip: Trip | undefined): {
  counts: TripCounts | null;
  plan: Resource<Itinerary>;
} {
  const plan = useActivePlan(trip);
  const past = trip ? archiveOnly(trip) : false;
  const tripId = trip?.id ?? "";
  const archive = useResource<ArchiveInfo>(past ? keys.archive(tripId) : null, (c) =>
    call(c.GET("/v1/trips/{trip_id}/archive", { params: { path: { trip_id: tripId } } })),
  );
  let counts: TripCounts | null;
  if (!trip) counts = null;
  else if (trip.selected_itinerary_id) {
    counts = plan.data ? countsFromItinerary(trip, plan.data) : null;
  } else if (past) counts = archive.data ? countsFromArchive(trip, archive.data) : null;
  else counts = countsWithoutPlan(trip);
  return { counts, plan };
}
