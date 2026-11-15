import type { Day, ItineraryVersion } from "@detour/shared";

import { type TripDocument, placeKey } from "../documents/model";

// Optimize a hand-made trip (ADR 029): which stops the sheet offers to keep in place, and when
// the menu offers Optimize and its undo. The shortest order itself is the server's work.

/** Fewer stops with a place than this leave nothing worth reordering. */
export const MIN_OPTIMIZE_STOPS = 3;

export type OptimizeStop = {
  id: string;
  name: string;
  day: number;
  /** Locked on the plan: it stays whatever the user picks, so it is shown as already kept. */
  locked: boolean;
  /** A document is about this place: it starts selected as "Keep in place" (ADR 029 rule 7). */
  hasDocument: boolean;
  kind: "visit" | "meal";
};

/** The stops of a plan that have a place, in day order. A free-time block is not one. */
export function optimizeStops(days: Day[], documents: TripDocument[]): OptimizeStop[] {
  const documented = new Set(
    documents.flatMap((d) => (d.link.kind === "place" ? [d.link.key] : [])),
  );
  const out: OptimizeStop[] = [];
  for (const day of [...days].sort((a, b) => a.day_index - b.day_index)) {
    for (const item of day.items) {
      if (item.type === "free_time") continue;
      out.push({
        id: item.id,
        name: item.display_name,
        day: day.day_index,
        locked: item.locked,
        hasDocument: documented.has(placeKey(item)),
        kind: item.type,
      });
    }
  }
  return out;
}

/** Optimize is offered from three stops with a place (ADR 029 rule 19). */
export function canOptimize(days: Day[]): boolean {
  return optimizeStops(days, []).length >= MIN_OPTIMIZE_STOPS;
}

/** The stops pre-selected as "Keep in place": those a document is about. Locked stops are kept by
 * the server anyway and are not listed as a choice. */
export function preselected(stops: OptimizeStop[]): string[] {
  return stops.filter((s) => s.hasDocument && !s.locked).map((s) => s.id);
}

/** "Undo Optimize" is offered while the plan's latest version came from applying Optimize, not
 * from an undo, and nothing changed it since. `versions` is newest first. */
export function canUndoOptimize(
  versions: ItineraryVersion[] | undefined,
  current: number,
): boolean {
  const latest = versions?.[0];
  return (
    latest !== undefined &&
    latest.action === "optimize" &&
    latest.restores_version == null &&
    latest.version === current - 1
  );
}
