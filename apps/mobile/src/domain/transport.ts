import type { Day, Item, TransportInfo } from "@detour/shared";

import type { IconName } from "../components/ds/Icon";
import { formatClock, formatMinutes } from "../util/format";
import { clockOf, minutesOf } from "./itinerary";

// Transport legs the user enters by hand (ADR 032): how they actually travelled, never computed.
// A length the user did not enter is unknown and is shown as such (hard constraint 5); there is
// no price, operator or booking (ADR 017).

export type TransportMode = TransportInfo["mode"];

export const TRANSPORT_MODES: TransportMode[] = [
  "train",
  "bus",
  "metro_tram",
  "ferry",
  "taxi",
  "walk",
  "other",
];

/** The same words as the backend's display name ("Train to Florence"). */
export const MODE_LABEL: Record<TransportMode, string> = {
  train: "Train",
  bus: "Bus",
  metro_tram: "Metro or tram",
  ferry: "Ferry",
  taxi: "Taxi or ride",
  walk: "Walk",
  other: "Transport",
};

export const MODE_ICON: Record<TransportMode, IconName> = {
  train: "transport",
  bus: "bus",
  metro_tram: "metro",
  ferry: "ferry",
  taxi: "taxi",
  walk: "walk",
  other: "route",
};

export const NOT_ENTERED = "time not entered";

export function isLeg(item: Item): item is Item & { transport: TransportInfo } {
  return item.type === "transport" && item.transport != null;
}

/** When a leg arrives, in minutes after its day's midnight (over 1440: the next day), or null. */
export function arrivalMinute(item: Item): number | null {
  const start = minutesOf(item.start_time);
  if (start === null || item.duration_minutes === null) return null;
  return start + item.duration_minutes;
}

/** "10:12 to 11:42", "22:30 to 07:10 the next day", "from 10:12", or null without a time. */
export function legTimes(item: Item): string | null {
  const start = formatClock(item.start_time);
  if (!start) return null;
  const end = arrivalMinute(item);
  if (end === null) return `from ${start}`;
  const clock = `${String(Math.floor(end / 60) % 24).padStart(2, "0")}:${String(end % 60).padStart(2, "0")}`;
  return end >= 24 * 60 ? `${start} to ${clock} the next day` : `${start} to ${clock}`;
}

/** The line in a day's list: "Train · 1 h 30 min · 10:12 to 11:42" or "Train · time not entered". */
export function legLine(item: Item): string {
  if (!isLeg(item)) return item.display_name;
  const parts = [MODE_LABEL[item.transport.mode]];
  parts.push(item.duration_minutes === null ? NOT_ENTERED : formatMinutes(item.duration_minutes));
  const times = legTimes(item);
  if (times) parts.push(times);
  return parts.join(" · ");
}

/** What a screen reader hears for a leg. */
export function legSentence(item: Item): string {
  if (!isLeg(item)) return item.display_name;
  const t = item.transport;
  const length =
    item.duration_minutes === null
      ? "Length not entered"
      : `${formatMinutes(item.duration_minutes)}`;
  const times = legTimes(item);
  return (
    `${MODE_LABEL[t.mode]} from ${t.from_name} to ${t.to_name}. ${length}.` +
    `${times ? ` ${times}.` : " Time not set."}${t.note ? ` Note: ${t.note}.` : ""} Entered by you.`
  );
}

/** The journey leg that covers a day's computed arrival (ADR 032), if the user entered one. */
export function journeyLeg(day: Day): Item | null {
  const id = day.arrival?.covered_by_item_id;
  if (id) return day.items.find((i) => i.id === id) ?? null;
  return day.items.find((i) => isLeg(i) && i.transport.is_journey) ?? null;
}

export type LegOnMap = {
  id: string;
  item: Item;
  mode: TransportMode;
  /** Where the mode icon sits: the middle of the line, or the one end that is known. */
  lngLat: [number, number];
  line: [number, number][] | null;
};

const located = (i: Item | undefined): [number, number] | null =>
  i && i.lat != null && i.lon != null ? [i.lon, i.lat] : null;

/** Each leg of a day on the map: a straight line from its from-point to its to-point; an end typed
 * by hand (no point) borrows the neighbouring stop; with neither end known nothing is drawn. */
export function legsOnMap(day: Day): LegOnMap[] {
  const out: LegOnMap[] = [];
  day.items.forEach((item, n) => {
    if (!isLeg(item)) return;
    const t = item.transport;
    const before = [...day.items.slice(0, n)].reverse().find((i) => located(i));
    const after = day.items.slice(n + 1).find((i) => located(i));
    const from: [number, number] | null =
      t.from_lat != null && t.from_lon != null ? [t.from_lon, t.from_lat] : located(before);
    const to: [number, number] | null =
      t.to_lat != null && t.to_lon != null ? [t.to_lon, t.to_lat] : located(after);
    if (!from && !to) return;
    const line = from && to && (from[0] !== to[0] || from[1] !== to[1]) ? [from, to] : null;
    const lngLat: [number, number] =
      from && to
        ? [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2]
        : ((from ?? to) as [number, number]);
    out.push({ id: item.id, item, mode: t.mode, lngLat, line });
  });
  return out;
}

// ---- where a leg goes in its day, and what its times run into (owner, 2026-11-16) -------------

/** An end of a leg as chosen on the form. */
export type LegEnd = { name: string; lat: number | null; lon: number | null };

const sameStop = (item: Item, end: LegEnd) =>
  item.type !== "transport" &&
  end.lat !== null &&
  item.display_name === end.name &&
  item.lat === end.lat &&
  item.lon === end.lon;

/**
 * Where a leg goes among the day's other items, as the 1-based position it will have:
 * 1. right after its From stop, when From is a stop of that day (it then replaces the walk or
 *    drive from that stop to the next);
 * 2. otherwise first, for a journey between cities;
 * 3. otherwise in time order by its start;
 * 4. otherwise after the last item.
 * `exceptId` leaves the leg itself out (when it is being changed).
 */
export function legPosition(
  day: Day | undefined,
  leg: { from: LegEnd | null; start: string | null; journey: boolean },
  exceptId?: string,
): number {
  const items = (day?.items ?? []).filter((i) => i.id !== exceptId);
  const from = leg.from;
  const after = from ? items.findIndex((i) => sameStop(i, from)) : -1;
  if (after >= 0) return after + 2;
  if (leg.journey) return 1;
  const start = minutesOf(leg.start);
  if (start !== null) {
    const later = items.findIndex((i) => {
      const s = minutesOf(i.start_time);
      return s !== null && s > start;
    });
    if (later >= 0) return later + 1;
  }
  return items.length + 1;
}

export type LegClash =
  | { kind: "none" }
  /** An item before the leg is still going when it leaves: the user changes a time. */
  | { kind: "earlier"; name: string; end: string }
  /** The leg runs into the items after it: they can all move `minutes` later. */
  | { kind: "later"; name: string; start: string; minutes: number; count: number }
  /** Moving them would take one past midnight. */
  | { kind: "midnight"; name: string; minutes: number };

const DAY_END = 24 * 60;

/** What a leg at `position` (1-based, as `legPosition` gives) with these times runs into. A leg
 * of unknown length is a point; one that arrives the next day runs to midnight. */
export function legClash(
  day: Day | undefined,
  position: number,
  leg: { start: string | null; minutes: number | null },
  exceptId?: string,
): LegClash {
  const start = minutesOf(leg.start);
  if (start === null) return { kind: "none" };
  const end = leg.minutes === null ? start : Math.min(start + leg.minutes, DAY_END);
  const items = (day?.items ?? []).filter((i) => i.id !== exceptId);
  const before = items.slice(0, position - 1);
  const after = items.slice(position - 1).filter((i) => minutesOf(i.start_time) !== null);
  for (const i of before) {
    const s = minutesOf(i.start_time);
    const e = i.end_time ? minutesOf(i.end_time) : s;
    // A point (length unknown) clashes only inside an item, as the server checks it.
    const overlaps = start === end ? s !== null && s < start : s !== null && s < end;
    if (s !== null && e !== null && overlaps && e > start) {
      return { kind: "earlier", name: i.display_name, end: clockOf(e) };
    }
  }
  if (after.length === 0) return { kind: "none" };
  const first = after.reduce((a, b) =>
    (minutesOf(b.start_time) as number) < (minutesOf(a.start_time) as number) ? b : a,
  );
  const firstStart = minutesOf(first.start_time) as number;
  const minutes = end - firstStart;
  if (minutes <= 0) return { kind: "none" };
  for (const i of after) {
    const s = minutesOf(i.start_time) as number;
    const e = minutesOf(i.end_time);
    // A night train already runs to midnight: only its start moves.
    const reach = (e === null || (i.type === "transport" && e < s) ? s : e) + minutes;
    if (reach > DAY_END - 1) return { kind: "midnight", name: i.display_name, minutes };
  }
  return {
    kind: "later",
    name: first.display_name,
    start: clockOf(firstStart),
    minutes,
    count: after.length,
  };
}
