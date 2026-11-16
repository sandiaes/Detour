import type {
  PlaceName,
  PlaceSuggestionRequest,
  PlaceSuggestions,
  ChangeSet,
  ChangeSetApplied,
  ChangeSetCreate,
  OptimizeRequest,
  Itinerary,
  ItemCreate,
  ItemUpdate,
  ItinerarySummary,
  UserPlace,
  UserPlaceCreate,
  UserPlaceUpdate,
} from "@detour/shared";
import { useCallback } from "react";

import { useBackend } from "../api/BackendProvider";
import { ApiError, NetworkError, call, callEmpty } from "../api/unwrap";
import { keys } from "./actions";
import { useData } from "./DataProvider";

// Adding and removing places (Phase 7, ADR 018). A change is previewed first: the server keeps it
// as a change set and returns the diff. Nothing changes in the plan until it is applied.

export const changeKey = (id: string) => `changeSet:${id}`;

/** The If-Match header for a plan change (ADR 034, step 4): the version this phone last read, so
 * a change made after someone else's is refused (409 plan_changed) instead of overwriting it. */
export function ifMatch(version: number | undefined): { "If-Match": string } | undefined {
  return version === undefined ? undefined : { "If-Match": `"${version}"` };
}

export function useChangeActions() {
  const { state } = useBackend();
  const data = useData();
  const client = state.phase === "ready" ? state.connection.client : null;

  const need = useCallback(() => {
    if (!client) throw new NetworkError("The server is not connected yet.");
    return client;
  }, [client]);

  /** Saves a pin, a town or an external search result as one of the user's places. */
  // The version of a plan held on this phone, if any.
  const versionOf = useCallback(
    (itineraryId: string) =>
      (data.memory.get(keys.itinerary(itineraryId))?.data as Itinerary | undefined)?.version,
    [data],
  );

  /** A plan someone else changed is read again, so the next try starts from what they did. */
  const guard = useCallback(
    async <T>(itineraryId: string, request: Promise<T>): Promise<T> => {
      try {
        return await request;
      } catch (e) {
        if (e instanceof ApiError && e.code === "plan_changed") {
          data.invalidate(keys.itinerary(itineraryId));
        }
        throw e;
      }
    },
    [data],
  );

  const savePlace = useCallback(
    async (body: UserPlaceCreate): Promise<UserPlace> =>
      call(need().POST("/v1/user-places", { body })),
    [need],
  );

  /** Changes a place the user saved (a restaurant being entered by hand, edited again). */
  const updatePlace = useCallback(
    async (id: string, body: UserPlaceUpdate): Promise<UserPlace> =>
      call(
        need().PATCH("/v1/user-places/{place_id}", { params: { path: { place_id: id } }, body }),
      ),
    [need],
  );

  /** Up to three days a place could go on, best first, from the Phase 7 recalculation (ADR 021).
   * Nothing is stored on the server. */
  const suggestPlaces = useCallback(
    async (itineraryId: string, body: PlaceSuggestionRequest): Promise<PlaceSuggestions> =>
      call(
        need().POST("/v1/itineraries/{itinerary_id}/place-suggestions", {
          params: { path: { itinerary_id: itineraryId } },
          body,
        }),
      ),
    [need],
  );

  const preview = useCallback(
    async (itineraryId: string, body: ChangeSetCreate): Promise<ChangeSet> => {
      const change = await call(
        need().POST("/v1/itineraries/{itinerary_id}/change-sets", {
          params: { path: { itinerary_id: itineraryId } },
          body,
        }),
      );
      data.put(changeKey(change.id), change);
      return change;
    },
    [need, data],
  );

  /** A shorter order of the plan's stops (ADR 029): previewed like any change, applied later. */
  const previewOptimize = useCallback(
    async (itineraryId: string, body: OptimizeRequest): Promise<ChangeSet> => {
      const change = await call(
        need().POST("/v1/itineraries/{itinerary_id}/optimize", {
          params: { path: { itinerary_id: itineraryId } },
          body,
        }),
      );
      data.put(changeKey(change.id), change);
      return change;
    },
    [need, data],
  );

  /** Restores the plan from before the latest Optimize, as a preview. */
  const previewOptimizeUndo = useCallback(
    async (itineraryId: string): Promise<ChangeSet> => {
      const change = await call(
        need().POST("/v1/itineraries/{itinerary_id}/optimize/undo", {
          params: { path: { itinerary_id: itineraryId } },
        }),
      );
      data.put(changeKey(change.id), change);
      return change;
    },
    [need, data],
  );

  /** Applies a previewed change. The new version of the plan comes back whole and is stored. */
  const apply = useCallback(
    async (tripId: string, changeSetId: string): Promise<ChangeSetApplied> => {
      const result = await call(
        need().POST("/v1/change-sets/{change_set_id}/apply", {
          params: { path: { change_set_id: changeSetId } },
        }),
      );
      const { days: _days, ...summary } = result.itinerary;
      data.put(changeKey(changeSetId), result.change_set);
      data.put(keys.itinerary(result.itinerary.id), result.itinerary);
      data.invalidate(keys.versions(result.itinerary.id));
      data.update<ItinerarySummary[]>(keys.itineraries(tripId), (list) =>
        list.map((s) => (s.id === summary.id ? summary : s)),
      );
      if (result.change_set.action === "edit_stops") {
        // The trip itself changed (its cities, name and length; ADR 024): read it again.
        data.invalidate(keys.trips);
        data.invalidate(keys.itineraries(tripId));
      }
      return result;
    },
    [need, data],
  );

  const discard = useCallback(
    async (changeSetId: string): Promise<ChangeSet> => {
      const change = await call(
        need().POST("/v1/change-sets/{change_set_id}/discard", {
          params: { path: { change_set_id: changeSetId } },
        }),
      );
      data.put(changeKey(changeSetId), change);
      return change;
    },
    [need, data],
  );

  /** Puts a place on a day at a time the user chose, with no proposal (the item endpoint). The
   * plan is read again afterwards. Used for empty (manual) plans, which cannot be recalculated,
   * and as a direct choice on any plan. */
  const addItem = useCallback(
    async (tripId: string, itineraryId: string, day: number, body: ItemCreate): Promise<void> => {
      await guard(
        itineraryId,
        call(
          need().POST("/v1/itineraries/{itinerary_id}/days/{day_index}/items", {
            params: {
              path: { itinerary_id: itineraryId, day_index: day },
              header: ifMatch(versionOf(itineraryId)),
            },
            body,
          }),
        ),
      );
      data.invalidate(keys.itinerary(itineraryId));
      data.invalidate(keys.itineraries(tripId));
    },
    [need, data, guard, versionOf],
  );

  /** Changes when a stop starts, how long it lasts and/or which day it is on (`dayIndex`). `minutes` undefined leaves the length
   * alone, null goes back to the default length; `startTime` ("HH:MM") and `position` (where the
   * stop now sits in the day's time order) are sent only when given. The plan is read again
   * afterwards: the end time of the stop changes. */
  const setSchedule = useCallback(
    async (
      itineraryId: string,
      itemId: string,
      change: {
        minutes?: number | null;
        startTime?: string;
        position?: number;
        dayIndex?: number;
      },
    ): Promise<void> => {
      const body: ItemUpdate = {};
      if (change.startTime !== undefined) body.start_time = `${change.startTime}:00`;
      if (change.position !== undefined) body.position = change.position;
      if (change.dayIndex !== undefined) body.day_index = change.dayIndex;
      if (change.minutes === null) body.use_default_duration = true;
      else if (change.minutes !== undefined) body.duration_minutes = change.minutes;
      await guard(
        itineraryId,
        call(
          need().PATCH("/v1/items/{item_id}", {
            params: { path: { item_id: itemId }, header: ifMatch(versionOf(itineraryId)) },
            body,
          }),
        ),
      );
      data.invalidate(keys.itinerary(itineraryId));
    },
    [need, data, guard, versionOf],
  );

  /** Sets how long a stop lasts (minutes), or goes back to its default length (null). */
  const setDuration = useCallback(
    (itineraryId: string, itemId: string, minutes: number | null): Promise<void> =>
      setSchedule(itineraryId, itemId, { minutes }),
    [setSchedule],
  );

  /** Takes a stop out of a plan made by hand, at once (a planned itinerary goes through a
   * previewed change set instead). */
  const removeItem = useCallback(
    async (tripId: string, itineraryId: string, itemId: string): Promise<void> => {
      await guard(
        itineraryId,
        callEmpty(
          need().DELETE("/v1/items/{item_id}", {
            params: { path: { item_id: itemId }, header: ifMatch(versionOf(itineraryId)) },
          }),
        ),
      );
      data.invalidate(keys.itinerary(itineraryId));
      data.invalidate(keys.itineraries(tripId));
    },
    [need, data, guard, versionOf],
  );

  /** Locks or unlocks an item: a locked item is never moved or removed by a recalculation. */
  const setLocked = useCallback(
    async (itineraryId: string, itemId: string, locked: boolean): Promise<void> => {
      const item = await guard(
        itineraryId,
        call(
          need().PATCH("/v1/items/{item_id}", {
            params: { path: { item_id: itemId }, header: ifMatch(versionOf(itineraryId)) },
            body: { locked },
          }),
        ),
      );
      data.update<Itinerary>(keys.itinerary(itineraryId), (it) => ({
        ...it,
        version: it.version + 1,
        days: it.days.map((d) => ({
          ...d,
          items: d.items.map((i) => (i.id === item.id ? { ...i, locked: item.locked } : i)),
        })),
      }));
    },
    [need, data, guard, versionOf],
  );

  /** Edit display name (ADR 025): the name this user approved for one imported place, or null to
   * go back to the resolved name. The original name is kept by the server; plans that name the
   * place follow, so they are read again. */
  const setDisplayName = useCallback(
    async (placeId: string, name: string | null): Promise<PlaceName> => {
      const params = { path: { place_id: placeId } };
      const result =
        name === null
          ? await call(need().DELETE("/v1/places/{place_id}/display-name", { params }))
          : await call(
              need().PUT("/v1/places/{place_id}/display-name", { params, body: { name } }),
            );
      data.invalidate("itinerary:");
      data.invalidate(`place:${placeId}`);
      return result;
    },
    [need, data],
  );

  return {
    setDisplayName,
    savePlace,
    updatePlace,
    suggestPlaces,
    preview,
    previewOptimize,
    previewOptimizeUndo,
    apply,
    discard,
    setLocked,
    setDuration,
    setSchedule,
    removeItem,
    addItem,
    connected: client !== null,
  };
}
