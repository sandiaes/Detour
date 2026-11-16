import type { Day, Item, TransportInfo } from "@detour/shared";

import type { IconName } from "../components/ds/Icon";
import { formatClock, formatMinutes } from "../util/format";
import { minutesOf } from "./itinerary";

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
