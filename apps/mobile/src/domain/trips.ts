import type { ArchiveInfo, Itinerary, Trip } from "@detour/shared";

// What the trips list and the trip overview say about a trip (ADR 021). Pure functions over what
// the backend returns: nothing is estimated or made up, and a figure that is not known is null.

export type TripTab = "upcoming" | "past";

export type TripPhase = "planning" | "upcoming" | "inProgress" | "past";

export const TRIP_PHASE_LABEL: Record<TripPhase, string> = {
  planning: "Planning",
  upcoming: "Upcoming",
  inProgress: "In progress",
  past: "Past",
};

/** Today on the device, as YYYY-MM-DD in local time. */
export function localToday(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Planning: no plan chosen yet. In progress: today is within the trip's dates. Past: the backend
 * says so (ADR 006). Otherwise Upcoming (including a chosen plan with no dates).
 */
export function tripPhase(trip: Trip, today: string = localToday()): TripPhase {
  if (trip.status === "past") return "past";
  if (!trip.selected_itinerary_id) return "planning";
  if (trip.start_date && trip.end_date && trip.start_date <= today && today <= trip.end_date) {
    return "inProgress";
  }
  return "upcoming";
}

/**
 * The trips in one tab. Upcoming: every trip that is not past, the soonest first and undated ones
 * last (newest first). Past: the most recent first.
 */
export function tripsInTab(trips: Trip[], tab: TripTab): Trip[] {
  if (tab === "upcoming") {
    return trips
      .filter((t) => t.status !== "past")
      .sort((a, b) => {
        if (a.start_date && b.start_date) {
          return a.start_date.localeCompare(b.start_date) || a.id.localeCompare(b.id);
        }
        if (a.start_date) return -1;
        if (b.start_date) return 1;
        return b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id);
      });
  }
  const key = (t: Trip) => t.start_date ?? t.archived_at ?? t.created_at;
  return trips
    .filter((t) => t.status === "past")
    .sort((a, b) => key(b).localeCompare(key(a)) || a.id.localeCompare(b.id));
}

/** What a trip contains. Null means not known (no plan, or not loaded). */
export type TripCounts = {
  days: number;
  cities: number | null;
  places: number | null;
  restaurants: number | null;
};

/**
 * Counts from the active plan: cities are the distinct base cities of its days (the destination
 * itself for a single-city trip), places the visits, restaurants the meals at a known place to eat.
 */
export function countsFromItinerary(trip: Trip, itinerary: Itinerary): TripCounts {
  const bases = new Set(
    itinerary.days.map((d) => d.base_city_name).filter((n): n is string => !!n),
  );
  let places = 0;
  let restaurants = 0;
  for (const day of itinerary.days) {
    for (const item of day.items) {
      if (item.type === "visit") places += 1;
      if (item.type === "meal" && (item.place_id || item.user_place_id || item.restaurant)) {
        restaurants += 1;
      }
    }
  }
  return {
    days: itinerary.days.length || trip.duration_days,
    cities: bases.size > 0 ? bases.size : trip.destination.kind === "city" ? 1 : null,
    places,
    restaurants,
  };
}

/** A past trip keeps its cities and attractions only; restaurants are not kept (ADR 006). */
export function countsFromArchive(trip: Trip, info: ArchiveInfo): TripCounts {
  return {
    days: trip.duration_days,
    cities: info.cities,
    places: info.attractions,
    restaurants: null,
  };
}

export function countsWithoutPlan(trip: Trip): TripCounts {
  return {
    days: trip.duration_days,
    cities: trip.destination.kind === "city" ? 1 : null,
    places: null,
    restaurants: null,
  };
}

/** "2 cities · 12 places · 4 restaurants", leaving out what is not known. */
export function countsLine(c: TripCounts): string | null {
  const parts: string[] = [];
  const add = (n: number | null, one: string, many: string) => {
    if (n !== null) parts.push(`${n} ${n === 1 ? one : many}`);
  };
  add(c.cities, "city", "cities");
  add(c.places, "place", "places");
  add(c.restaurants, "restaurant", "restaurants");
  return parts.length > 0 ? parts.join(" · ") : null;
}

/** "1–2 May 2027 · 2 days" for a card; "2 days" without dates. */
export function shortSpan(trip: Trip): string {
  const days = `${trip.duration_days} ${trip.duration_days === 1 ? "day" : "days"}`;
  const s = trip.start_date;
  const e = trip.end_date;
  if (!s || !e) return days;
  const MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const [sy, sm, sd] = s.split("-").map(Number) as [number, number, number];
  const [ey, em, ed] = e.split("-").map(Number) as [number, number, number];
  const month = (m: number) => MONTHS[m - 1] ?? "";
  let range: string;
  if (sy === ey && sm === em)
    range = sd === ed ? `${sd} ${month(sm)} ${sy}` : `${sd}–${ed} ${month(sm)} ${sy}`;
  else if (sy === ey) range = `${sd} ${month(sm)} – ${ed} ${month(em)} ${sy}`;
  else range = `${sd} ${month(sm)} ${sy} – ${ed} ${month(em)} ${ey}`;
  return `${range} · ${days}`;
}
