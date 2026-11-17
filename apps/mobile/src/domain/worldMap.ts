import type { Trip } from "@detour/shared";

// The Map tab: every place the user has been to or is going to, one point per city (a multi-city
// trip contributes each of its cities). Pure functions over the trips the backend returns; nothing
// is estimated. A place visited on several trips is one point.

export type WorldPoint = {
  id: string;
  name: string;
  lngLat: [number, number];
  /** "been": on a past trip. "going": on a trip that is not past (planned, upcoming, in progress). */
  state: "been" | "going";
  /** The trips that name this place, newest first. */
  trips: { id: string; title: string }[];
};

/** Rounded so the same city from two trips (two lookups) lands on one point. */
function keyOf(name: string, lat: number, lon: number): string {
  return `${name.trim().toLowerCase()}|${lat.toFixed(1)}|${lon.toFixed(1)}`;
}

export function worldPoints(trips: Trip[]): WorldPoint[] {
  const byKey = new Map<string, WorldPoint>();
  const ordered = [...trips]
    .filter((t) => !t.is_seed)
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id));
  for (const trip of ordered) {
    const state = trip.status === "past" ? "been" : "going";
    const places =
      trip.stops && trip.stops.length > 0
        ? trip.stops.map((s) => ({ name: s.name, lat: s.lat, lon: s.lon }))
        : [{ name: trip.destination.name, lat: trip.destination.lat, lon: trip.destination.lon }];
    for (const p of places) {
      const key = keyOf(p.name, p.lat, p.lon);
      const found = byKey.get(key);
      const ref = { id: trip.id, title: trip.title };
      if (found) {
        // A place already visited stays "been" only if every trip that names it is past.
        if (state === "going") found.state = "going";
        if (!found.trips.some((t) => t.id === trip.id)) found.trips.push(ref);
      } else {
        byKey.set(key, {
          id: key,
          name: p.name,
          lngLat: [p.lon, p.lat],
          state,
          trips: [ref],
        });
      }
    }
  }
  return [...byKey.values()].sort((a, b) => a.id.localeCompare(b.id));
}

export function worldSummary(points: WorldPoint[]): { been: number; going: number } {
  return {
    been: points.filter((p) => p.state === "been").length,
    going: points.filter((p) => p.state === "going").length,
  };
}
