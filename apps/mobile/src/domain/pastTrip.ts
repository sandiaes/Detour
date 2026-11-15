import type { TripVisit } from "@detour/shared";
import { dayTones } from "../theme";
import { formatMinutes } from "../util/format";

// What a past trip shows (ADR 006, ADR 026): the archived cities and stops on a map, as a day
// record (what was done on which day, with the start and length when they were kept) and as a list
// grouped by city. The archive keeps snapshots only: no routes or travel times.

export const VISIT_KIND_LABEL: Record<TripVisit["kind"], string> = {
  city: "City",
  attraction: "Attraction",
  restaurant: "Restaurant",
  cafe: "Café",
};

export type VisitGroup = {
  /** The city's visit id, or "all" when the archive has no city. */
  key: string;
  name: string;
  /** The archived city row; null when the archive has none (an area trip without a plan). */
  city: TripVisit | null;
  /** Stops (attractions, restaurants, cafés), by day. */
  visits: TripVisit[];
};

/** Squared distance in degrees, longitude scaled by latitude. Only used to compare. */
function distance2(a: TripVisit, b: TripVisit): number {
  const dx = (a.lon - b.lon) * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  const dy = a.lat - b.lat;
  return dx * dx + dy * dy;
}

/**
 * The visits grouped by city: each city once, and each attraction under the nearest city of the
 * archive (the archive does not say which city a stop belonged to; nearest is what a map shows).
 * Cities are in the order of the archive (by day), attractions by day within a city. Without a
 * city row there is one group named `fallbackName`.
 */
export function groupVisitsByCity(visits: TripVisit[], fallbackName: string): VisitGroup[] {
  const cities = visits.filter((v) => v.kind === "city");
  const attractions = visits.filter((v) => v.kind !== "city");
  if (cities.length === 0) {
    return attractions.length === 0
      ? []
      : [{ key: "all", name: fallbackName, city: null, visits: attractions }];
  }
  const groups: VisitGroup[] = cities.map((c) => ({
    key: c.id,
    name: c.name,
    city: c,
    visits: [],
  }));
  for (const a of attractions) {
    let best = groups[0] as VisitGroup;
    let bestDistance = Infinity;
    for (const g of groups) {
      const d = distance2(a, g.city as TripVisit);
      if (d < bestDistance) {
        best = g;
        bestDistance = d;
      }
    }
    best.visits.push(a);
  }
  return groups;
}

export type VisitCounts = {
  cities: number;
  attractions: number;
  placesToEat: number;
  skipped: number;
};

/** Visited cities, attractions and places to eat (not cleared by the user), and how many were
 * cleared. */
export function visitCounts(visits: TripVisit[]): VisitCounts {
  const counts = { cities: 0, attractions: 0, placesToEat: 0, skipped: 0 };
  for (const v of visits) {
    if (!v.confirmed) counts.skipped += 1;
    else if (v.kind === "city") counts.cities += 1;
    else if (v.kind === "attraction") counts.attractions += 1;
    else counts.placesToEat += 1;
  }
  return counts;
}

export type RecordDay = { day: number; stops: TripVisit[] };

/**
 * The day record: the stops of each day in the order they were planned (cities are base-city rows
 * with no place in the day and are left out). A stop archived before the record existed has no
 * order; it follows the ordered ones, by name. Days with no stop are not listed.
 */
export function dayRecord(visits: TripVisit[]): RecordDay[] {
  const byDay = new Map<number, TripVisit[]>();
  for (const v of visits) {
    if (v.kind === "city") continue;
    byDay.set(v.day_number, [...(byDay.get(v.day_number) ?? []), v]);
  }
  const order = (v: TripVisit) => v.position ?? Number.MAX_SAFE_INTEGER;
  return [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([day, stops]) => ({
      day,
      stops: [...stops].sort((a, b) => order(a) - order(b) || a.name.localeCompare(b.name)),
    }));
}

/** "Café · 11:00 · 45 min", or just "Attraction" when no time was kept. */
export function stopRecordLine(v: TripVisit): string {
  const parts: string[] = [VISIT_KIND_LABEL[v.kind]];
  if (v.start_time) parts.push(v.start_time);
  if (v.duration_minutes) parts.push(formatMinutes(v.duration_minutes));
  return parts.join(" · ");
}

export type PastPoint = {
  id: string;
  name: string;
  kind: TripVisit["kind"];
  day: number;
  lngLat: [number, number];
};

/** The map's markers: the visits that were not cleared. Cities first, so attractions draw over. */
export function visitedPoints(visits: TripVisit[]): PastPoint[] {
  return visits
    .filter((v) => v.confirmed)
    .map((v) => ({
      id: v.id,
      name: v.name,
      kind: v.kind,
      day: v.day_number,
      lngLat: [v.lon, v.lat] as [number, number],
    }))
    .sort((a, b) => Number(b.kind === "city") - Number(a.kind === "city"));
}

/** One colour per day, so a day's stops read together on the map and in the lists (`dayTones` in
 * theme.ts). They repeat after eight days; every use also says the day in words. */
export const DAY_COLORS = dayTones.map((t) => t.fg);

function dayIndex(day: number): number {
  return ((((Math.trunc(day) || 1) - 1) % dayTones.length) + dayTones.length) % dayTones.length;
}

export function dayColor(day: number): string {
  return (dayTones[dayIndex(day)] as (typeof dayTones)[number]).fg;
}

/** The soft ground of a day's colour, for a tile behind its icon. */
export function daySoft(day: number): string {
  return (dayTones[dayIndex(day)] as (typeof dayTones)[number]).bg;
}
