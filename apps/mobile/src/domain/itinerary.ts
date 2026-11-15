import type { Day, Item, Transfer } from "@detour/shared";

export type DayRow =
  | { kind: "item"; key: string; item: Item; ordinal: number | null }
  | { kind: "transfer"; key: string; from: Item; to: Item | null; transfer: Transfer }
  | { kind: "free"; key: string; start: string; end: string; minutes: number };

/** An idle stretch shorter than this is slack, not free time (ADR 026, decision 5). */
export const MIN_FREE_MINUTES = 30;

function minutesOf(time: string | null | undefined): number | null {
  const m = /^(\d{2}):(\d{2})/.exec(time ?? "");
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

function clockOf(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

/**
 * The idle stretch between two stops, after the travel between them: the midday gap of a generated
 * plan, or any gap in a plan made by hand. It is not stored; it is read from the times (ADR 026,
 * design §5). Null when a time is missing or the stretch is shorter than `MIN_FREE_MINUTES`.
 */
export function freeStretch(
  from: Item,
  to: Item,
): { start: string; end: string; minutes: number } | null {
  const end = minutesOf(from.end_time);
  const next = minutesOf(to.start_time);
  if (end === null || next === null) return null;
  const travel = from.transfer ? Math.ceil(from.transfer.seconds / 60) : 0;
  const start = end + travel;
  const minutes = next - start;
  return minutes >= MIN_FREE_MINUTES
    ? { start: clockOf(start), end: clockOf(next), minutes }
    : null;
}

/**
 * One flat list per day: an item, then the transfer to the next one (if the backend computed it),
 * then a "Free time" row when the stops leave an idle stretch of 30 minutes or more.
 * `ordinal` numbers the items that have a place, so the number on a list row matches the number on
 * the map marker.
 */
export function buildDayRows(day: Day): DayRow[] {
  const byId = new Map(day.items.map((i) => [i.id, i]));
  const rows: DayRow[] = [];
  let ordinal = 0;
  for (const item of day.items) {
    const located = item.lat !== null && item.lon !== null;
    rows.push({ kind: "item", key: item.id, item, ordinal: located ? ++ordinal : null });
    if (item.transfer) {
      rows.push({
        kind: "transfer",
        key: `${item.id}>${item.transfer.to_item_id}`,
        from: item,
        to: byId.get(item.transfer.to_item_id) ?? null,
        transfer: item.transfer,
      });
    }
    const next = day.items[day.items.indexOf(item) + 1];
    if (next && item.type !== "free_time" && next.type !== "free_time") {
      const free = freeStretch(item, next);
      if (free) rows.push({ kind: "free", key: `${item.id}~free`, ...free });
    }
  }
  return rows;
}

export type DayTotals = {
  visits: number;
  meals: number;
  visitMinutes: number;
  travelSeconds: number;
};

/** Travel includes the drive from the previous base city that starts the day (area trips). */
export function dayTotals(day: Day): DayTotals {
  let visits = 0;
  let meals = 0;
  let visitMinutes = 0;
  let travelSeconds = day.arrival?.seconds ?? 0;
  for (const item of day.items) {
    if (item.type === "visit") {
      visits += 1;
      visitMinutes += item.duration_minutes;
    }
    if (item.type === "meal") meals += 1;
    if (item.transfer) travelSeconds += item.transfer.seconds;
  }
  return { visits, meals, visitMinutes, travelSeconds };
}

/** What a stop is, for telling sights from places to eat (map and day list). */
export type StopKind = "attraction" | "restaurant" | "cafe" | "other";

export const STOP_KIND_LABEL: Record<StopKind, string> = {
  attraction: "Attraction",
  restaurant: "Restaurant",
  cafe: "Café",
  other: "Stop",
};

export function stopKind(item: Item): StopKind {
  if (item.type === "meal") return item.restaurant?.venue_type === "cafe" ? "cafe" : "restaurant";
  return item.type === "visit" ? "attraction" : "other";
}

/** Restaurants and cafés are one group on the map: places to eat. */
export const isEatKind = (kind: StopKind): boolean => kind === "restaurant" || kind === "cafe";

export type MapPoint = {
  id: string;
  kind: StopKind;
  ordinal: number;
  name: string;
  lngLat: [number, number];
  start: string | null;
  item: Item;
};

export function mapPoints(day: Day): MapPoint[] {
  const points: MapPoint[] = [];
  for (const row of buildDayRows(day)) {
    if (row.kind !== "item" || row.ordinal === null) continue;
    const { item } = row;
    points.push({
      id: item.id,
      kind: stopKind(item),
      ordinal: row.ordinal,
      name: item.display_name,
      lngLat: [item.lon as number, item.lat as number],
      start: item.start_time ?? null,
      item,
    });
  }
  return points;
}

export type TransferFeature = {
  type: "Feature";
  id: string;
  properties: { confidence: Transfer["confidence"]; mode: Transfer["mode"] };
  geometry: { type: "LineString"; coordinates: [number, number][] };
};

/**
 * Straight connectors between the stops of a transfer. The backend does not return route
 * geometry for these transfers (ADR 013: geometry is not stored, and no endpoint serves it), so a
 * line joins the two stops directly. Whether the *time* is routed or estimated is the property
 * `confidence`; the map draws routed solid and estimated dashed.
 */
export function transferFeatures(day: Day): TransferFeature[] {
  const points = new Map(mapPoints(day).map((p) => [p.id, p]));
  const features: TransferFeature[] = [];
  for (const item of day.items) {
    const t = item.transfer;
    const from = points.get(item.id);
    const to = t ? points.get(t.to_item_id) : undefined;
    if (!t || !from || !to) continue;
    features.push({
      type: "Feature",
      id: `${item.id}>${t.to_item_id}`,
      properties: { confidence: t.confidence, mode: t.mode },
      geometry: { type: "LineString", coordinates: [from.lngLat, to.lngLat] },
    });
  }
  return features;
}

/** [west, south, east, north] around the points, or null when there are none. */
export function boundsOf(
  points: { lngLat: [number, number] }[],
): [number, number, number, number] | null {
  if (points.length === 0) return null;
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const { lngLat } of points) {
    w = Math.min(w, lngLat[0]);
    e = Math.max(e, lngLat[0]);
    s = Math.min(s, lngLat[1]);
    n = Math.max(n, lngLat[1]);
  }
  return [w, s, e, n];
}

export function modeLabel(mode: Transfer["mode"]): string {
  return mode === "walk" ? "Walk" : "Drive";
}

export function confidenceLabel(confidence: Transfer["confidence"]): string {
  return confidence === "routed" ? "routed" : "estimated";
}

/** The travel that starts a day at a new base city (area trips), placed at that city. */
export type TransportPoint = {
  id: string;
  dayId: string;
  name: string;
  fromName: string | null;
  lngLat: [number, number];
  /** The previous base city, when its position is known: the leg is drawn from there. */
  fromLngLat: [number, number] | null;
  arrival: NonNullable<Day["arrival"]>;
};

export const transportId = (day: Day) => `arrival-${day.id}`;

/**
 * The transport marker of a day: its arrival at the base city, when the backend gives the city's
 * position. Nothing is placed when the position is unknown; the list still shows the journey.
 */
export function transportPoint(day: Day, previous: Day | undefined): TransportPoint | null {
  const a = day.arrival;
  if (!a || day.base_city_lat == null || day.base_city_lon == null) return null;
  const from =
    previous && previous.base_city_lat != null && previous.base_city_lon != null
      ? ([previous.base_city_lon, previous.base_city_lat] as [number, number])
      : null;
  return {
    id: transportId(day),
    dayId: day.id,
    name: day.base_city_name ?? "Next base",
    fromName: a.from_base_city_name,
    lngLat: [day.base_city_lon, day.base_city_lat],
    fromLngLat: from,
    arrival: a,
  };
}

/** The leg of a transport point as a line, when both ends are known. */
export function transportFeature(point: TransportPoint): TransferFeature | null {
  if (!point.fromLngLat) return null;
  const { confidence, mode } = point.arrival;
  // A leg with no known time (ADR 024) is a marker without a line: nothing suggests a route.
  if (confidence === "unknown" || mode === "unknown") return null;
  return {
    type: "Feature",
    id: point.id,
    properties: { confidence, mode },
    geometry: { type: "LineString", coordinates: [point.fromLngLat, point.lngLat] },
  };
}
