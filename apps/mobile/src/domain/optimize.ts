import type { ChangeSet, Day, Item, ItineraryVersion } from "@detour/shared";

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
      // Free time and transport legs never move (ADR 029, ADR 032).
      if (item.type === "free_time" || item.type === "transport") continue;
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

// ---- the preview of an Optimize (ADR 029) -----------------------------------------------------------

/** The server's proposed order for an Optimize preview (`ChangeSet.proposed`). */
export type ProposedOrder = NonNullable<ChangeSet["proposed"]>;

/**
 * The plan as Optimize proposes it: the same days and stops, in the proposed day, order and times,
 * with the proposed travel between them. Nothing is computed here that the server did not say;
 * a stop is found by its id, so a stop the proposal does not mention is dropped from the picture.
 */
export function proposedDays(days: Day[], proposed: ProposedOrder): Day[] {
  const items = new Map(days.flatMap((d) => d.items.map((i) => [i.id, i] as const)));
  const transfers = new Map(proposed.transfers.map((t) => [t.from_item_id, t] as const));
  const starts = new Map((proposed.starts ?? []).map((t) => [t.day_index, t] as const));
  return days.map((day) => {
    const morning = starts.get(day.day_index);
    const stops = proposed.stops
      .filter((s) => s.day_index === day.day_index && items.has(s.item_id))
      .sort((a, b) => a.position - b.position);
    return {
      ...day,
      start: morning
        ? {
            stay_id: morning.stay_id,
            name: morning.name,
            lat: morning.lat,
            lon: morning.lon,
            to_item_id: morning.to_item_id,
            mode: morning.mode,
            seconds: morning.seconds,
            meters: morning.meters,
            confidence: morning.confidence,
          }
        : null,
      items: stops.map((s, position) => {
        const item = items.get(s.item_id) as Item;
        const t = transfers.get(s.item_id);
        return {
          ...item,
          day_id: day.id,
          position,
          start_time: s.start_time ?? null,
          end_time: s.end_time ?? null,
          transfer: t
            ? {
                to_item_id: t.to_item_id,
                mode: t.mode,
                seconds: t.seconds,
                meters: t.meters,
                confidence: t.confidence,
              }
            : null,
        };
      }),
    };
  });
}

/** Travel metres over every transfer of the days, and the mornings from the stays. */
export function travelMeters(days: Day[]): number {
  return days.reduce(
    (sum, d) =>
      sum + (d.start?.meters ?? 0) + d.items.reduce((s, i) => s + (i.transfer?.meters ?? 0), 0),
    0,
  );
}

/** "12 km", "850 m": a distance in words. */
export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters / 10) * 10} m`;
  const km = meters / 1000;
  return `${km >= 10 ? Math.round(km) : Math.round(km * 10) / 10} km`;
}
