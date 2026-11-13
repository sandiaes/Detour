import type { TripVisit } from "@detour/shared";

// What a past trip shows (ADR 006): the archived cities and attractions on a map, and as a list
// grouped by city. The archive keeps snapshots only: no routes, travel times or times of day.

export const VISIT_KIND_LABEL: Record<TripVisit["kind"], string> = {
  city: "City",
  attraction: "Attraction",
};

export type VisitGroup = {
  /** The city's visit id, or "all" when the archive has no city. */
  key: string;
  name: string;
  /** The archived city row; null when the archive has none (an area trip without a plan). */
  city: TripVisit | null;
  /** Attractions, by day. */
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
  const attractions = visits.filter((v) => v.kind === "attraction");
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

export type VisitCounts = { cities: number; attractions: number; skipped: number };

/** Visited cities and attractions (not cleared by the user), and how many were cleared. */
export function visitCounts(visits: TripVisit[]): VisitCounts {
  const counts = { cities: 0, attractions: 0, skipped: 0 };
  for (const v of visits) {
    if (!v.confirmed) counts.skipped += 1;
    else if (v.kind === "city") counts.cities += 1;
    else counts.attractions += 1;
  }
  return counts;
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
