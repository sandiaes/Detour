import type { Item } from "@detour/shared";
import { useCallback, useState } from "react";

import { describeError, planningIssues } from "../api/unwrap";
import { useNavigation } from "../nav/Navigator";
import { useChangeActions } from "./changes";

/** Lock and remove for the stops of a plan (Phase 7). Removing always goes through a preview. */
export type ItemActions = {
  onToggleLock: (item: Item) => void;
  onRemove: (item: Item) => void;
  /** The item whose lock or removal is being sent. */
  busyId: string | null;
};

export function useItemActions(tripId: string, itineraryId: string) {
  const nav = useNavigation();
  const changeActions = useChangeActions();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [issues, setIssues] = useState<string[]>([]);

  const toggleLock = useCallback(
    async (item: Item) => {
      setBusyId(item.id);
      setProblem(null);
      setIssues([]);
      try {
        await changeActions.setLocked(itineraryId, item.id, !item.locked);
      } catch (e) {
        setProblem(describeError(e));
      } finally {
        setBusyId(null);
      }
    },
    [changeActions, itineraryId],
  );

  const remove = useCallback(
    async (item: Item) => {
      setBusyId(item.id);
      setProblem(null);
      setIssues([]);
      try {
        const change = await changeActions.preview(itineraryId, {
          action: "remove_place",
          item_id: item.id,
        });
        nav.push({ name: "changePreview", tripId, itineraryId, changeSetId: change.id });
      } catch (e) {
        setProblem(describeError(e));
        setIssues(planningIssues(e));
      } finally {
        setBusyId(null);
      }
    },
    [changeActions, nav, itineraryId, tripId],
  );

  const actions: ItemActions = {
    onToggleLock: (i) => void toggleLock(i),
    onRemove: (i) => void remove(i),
    busyId,
  };
  return {
    actions,
    connected: changeActions.connected,
    /** The last failure, with the planner's issues, as one sentence; null when none. */
    problem: problem ? [problem, ...issues].join(" ") : null,
  };
}
