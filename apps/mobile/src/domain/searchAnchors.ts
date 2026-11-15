import type { Day, PlaceSummary, Trip } from "@detour/shared";

// Where a search for places to add is centred (owner, 2026-11-15). A multi-city trip (ADR 024) has
// one city per stop: a sight is searched around each of them, and a day's own city comes first and
// is the one distances are measured from. A one-city trip searches around its destination.

/** A city a search is centred on. */
export type Anchor = { name: string; lat: number; lon: number };

/** Sights are searched within this distance of each of the trip's cities. */
export const LOCAL_RADIUS_M = 50_000;

const EARTH_RADIUS_M = 6_371_008.8;

/** The great-circle distance in metres (a straight line, never a route). */
export function distanceMeters(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Every city the trip stays in, in the trip's order and each once; else its destination. */
export function tripAnchors(trip: Trip | undefined): Anchor[] {
  if (!trip) return [];
  const seen = new Set<number>();
  const stops: Anchor[] = [];
  for (const s of [...(trip.stops ?? [])].sort((a, b) => a.position - b.position)) {
    if (seen.has(s.city_id)) continue;
    seen.add(s.city_id);
    stops.push({ name: s.name, lat: s.lat, lon: s.lon });
  }
  if (stops.length > 0) return stops;
  const d = trip.destination;
  return [{ name: d.name, lat: d.lat, lon: d.lon }];
}

/** The city a day is based in: its base city when the plan has one (a multi-city trip), else the
 * trip's only city. Null when the day is not known and the trip has more than one city. */
export function dayAnchor(
  trip: Trip | undefined,
  days: Day[] | undefined,
  dayIndex: number | undefined,
): Anchor | null {
  const anchors = tripAnchors(trip);
  const day = dayIndex === undefined ? undefined : days?.find((d) => d.day_index === dayIndex);
  if (day && day.base_city_lat != null && day.base_city_lon != null) {
    return {
      name: day.base_city_name ?? "the day's city",
      lat: day.base_city_lat,
      lon: day.base_city_lon,
    };
  }
  return anchors.length === 1 ? (anchors[0] as Anchor) : null;
}

/** The anchors to search around, the day's city first. */
export function searchAnchors(all: Anchor[], focus: Anchor | null): Anchor[] {
  if (!focus) return all;
  const near = (a: Anchor) => distanceMeters(a, focus) < 1_000;
  return [focus, ...all.filter((a) => !near(a))];
}

/** A sight with the city its distance is told from. */
export type RankedSight = { place: PlaceSummary; from: Anchor; meters: number };

const TIER: Record<NonNullable<PlaceSummary["match"]>, number> = {
  exact: 0,
  prefix: 1,
  word_prefix: 2,
  contains: 3,
  similar: 4,
};

/**
 * One list from the searches around each anchor: each sight once, its distance from the day's
 * city when a day is chosen (else from the nearest of the trip's cities). The sights of the day's
 * city come first, then the best name matches, then the nearest.
 */
export function mergeSights(
  lists: { anchor: Anchor; results: PlaceSummary[] }[],
  focus: Anchor | null,
  limit = 8,
): RankedSight[] {
  const byId = new Map<string, RankedSight>();
  for (const { results } of lists) {
    for (const place of results) {
      if (byId.has(place.id)) continue;
      const candidates = focus ? [focus] : lists.map((l) => l.anchor);
      let best: RankedSight | null = null;
      for (const from of candidates) {
        const meters = distanceMeters(from, place);
        if (!best || meters < best.meters) best = { place, from, meters };
      }
      if (best) byId.set(place.id, best);
    }
  }
  // "In the day's city": within the radius the search used around it.
  const local = (s: RankedSight) => (focus && s.meters <= LOCAL_RADIUS_M ? 0 : 1);
  return [...byId.values()]
    .sort(
      (a, b) =>
        local(a) - local(b) ||
        (TIER[a.place.match ?? "similar"] ?? 4) - (TIER[b.place.match ?? "similar"] ?? 4) ||
        a.meters - b.meters ||
        (a.place.id < b.place.id ? -1 : a.place.id > b.place.id ? 1 : 0),
    )
    .slice(0, limit);
}
