import type { DestinationResult, ExternalPlace, Trip, TripCreate } from "@detour/shared";

import { parseCoordinate } from "./restaurants";

// Destinations (ADR 027). A trip can be made for any place: the ones in an imported, available
// region can be planned (suggestions), every other place is an empty trip filled by hand. The
// destination of such a trip is a snapshot with a provider-prefixed reference.

/** What the user chose as a destination: an imported city or area, or a place from outside. */
export type Choice = Omit<DestinationResult, "kind"> & {
  kind: "city" | "area" | "place";
};

export const NOT_PLANNABLE_HINT = "No sight data for this place: you add the places yourself.";

/** Why suggestions are not offered for this choice, or null when they are. */
export function notPlannableReason(c: Choice): string | null {
  if (c.kind === "place") return NOT_PLANNABLE_HINT;
  if (c.unavailable_reason === "area_single_city_only") {
    return "Areas in Japan cannot be planned yet (rail travel is not modelled). Choose a city.";
  }
  if (c.unavailable_reason === "region_not_available" || !c.planning_available) {
    return "No sight data for this region yet: you add the places yourself.";
  }
  return null;
}

export const isPlannable = (c: Choice): boolean => notPlannableReason(c) === null;

/** A Photon result as a choice. It has no imported data, so it is never plannable. */
export function choiceFromExternal(p: ExternalPlace): Choice | null {
  if (!p.ref) return null;
  return {
    kind: "place",
    ref: `photon:${p.ref}`,
    name: p.name,
    country_iso2: p.country_code,
    country_name: p.country,
    admin1_name: p.state ?? p.city,
    population: null,
    admin_level: null,
    lat: p.lat,
    lon: p.lon,
    region_id: null,
    planning_available: false,
    unavailable_reason: null,
    match: "similar",
  };
}

/** A destination typed in by hand: a name and typed coordinates (ADR 027, decision 15). */
export function manualChoice(name: string): Choice {
  return {
    kind: "place",
    ref: "manual",
    name,
    country_iso2: null,
    country_name: null,
    admin1_name: null,
    population: null,
    admin_level: null,
    lat: 0,
    lon: 0,
    region_id: null,
    planning_available: false,
    unavailable_reason: null,
    match: "similar",
  };
}

/** The coordinates typed for a manual destination, or null while they are not both valid. */
export function manualPoint(lat: string, lon: string): { lat: number; lon: number } | null {
  const a = parseCoordinate(lat, "lat");
  const b = parseCoordinate(lon, "lon");
  return a === null || b === null ? null : { lat: a, lon: b };
}

/** The body that creates a trip for this choice. An unplannable imported place becomes a place
 * trip with a gazetteer reference; a plannable one stays a city or area trip. */
export function tripBody(
  choice: Choice,
  start: { days: number; startDate: string | null },
  asPlace: boolean,
): TripCreate {
  const base = {
    title: choice.name,
    duration_days: start.days,
    start_date: start.startDate,
  };
  if (choice.kind === "place" || asPlace) {
    const ref =
      choice.kind === "place"
        ? choice.ref
        : `${choice.kind === "area" ? "area" : "geonames"}:${choice.ref}`;
    return {
      ...base,
      destination_kind: "place",
      destination_ref: ref,
      destination_name: choice.name,
      destination_lat: choice.lat,
      destination_lon: choice.lon,
      ...(choice.country_iso2 ? { destination_country: choice.country_iso2 } : {}),
    };
  }
  return { ...base, destination_kind: choice.kind, destination_ref: choice.ref };
}

/** The photo sources of a place trip: only a gazetteer place has candidates (ADR 027). */
export function placeCoverSource(
  trip: Trip,
): { kind: "city" | "area"; ref: string; name: string } | null {
  const { ref, name } = trip.destination;
  if (ref.startsWith("geonames:")) return { kind: "city", ref: ref.slice(9), name };
  if (ref.startsWith("area:")) return { kind: "area", ref: ref.slice(5), name };
  return null;
}

/** A trip to a place outside the imported data: empty by nature, no suggestions (ADR 027). */
export const isPlaceTrip = (trip: Trip): boolean => trip.destination.kind === "place";
