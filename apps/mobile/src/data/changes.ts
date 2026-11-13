import type {
  ChangeSet,
  ChangeSetApplied,
  ChangeSetCreate,
  Itinerary,
  ItinerarySummary,
  UserPlace,
  UserPlaceCreate,
} from "@detour/shared";
import { useCallback } from "react";

import { useBackend } from "../api/BackendProvider";
import { NetworkError, call } from "../api/unwrap";
import { keys } from "./actions";
import { useData } from "./DataProvider";

// Adding and removing places (Phase 7, ADR 018). A change is previewed first: the server keeps it
// as a change set and returns the diff. Nothing changes in the plan until it is applied.

export const changeKey = (id: string) => `changeSet:${id}`;

export function useChangeActions() {
  const { state } = useBackend();
  const data = useData();
  const client = state.phase === "ready" ? state.connection.client : null;

  const need = useCallback(() => {
    if (!client) throw new NetworkError("The server is not connected yet.");
    return client;
  }, [client]);

  /** Saves a pin, a town or an external search result as one of the user's places. */
  const savePlace = useCallback(
    async (body: UserPlaceCreate): Promise<UserPlace> =>
      call(need().POST("/v1/user-places", { body })),
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
      data.update<ItinerarySummary[]>(keys.itineraries(tripId), (list) =>
        list.map((s) => (s.id === summary.id ? summary : s)),
      );
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

  /** Locks or unlocks an item: a locked item is never moved or removed by a recalculation. */
  const setLocked = useCallback(
    async (itineraryId: string, itemId: string, locked: boolean): Promise<void> => {
      const item = await call(
        need().PATCH("/v1/items/{item_id}", {
          params: { path: { item_id: itemId } },
          body: { locked },
        }),
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
    [need, data],
  );

  return { savePlace, preview, apply, discard, setLocked, connected: client !== null };
}
