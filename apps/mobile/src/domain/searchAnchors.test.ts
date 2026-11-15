import type { Day, PlaceSummary, Trip } from "@detour/shared";

import {
  dayAnchor,
  distanceMeters,
  mergeSights,
  searchAnchors,
  tripAnchors,
} from "./searchAnchors";

const ROME = { name: "Rome", lat: 41.9028, lon: 12.4964 };
const FLORENCE = { name: "Florence", lat: 43.7696, lon: 11.2558 };

const trip = {
  destination: { kind: "route", ref: null, name: "Rome to Florence", lat: 41.9, lon: 12.5 },
  stops: [
    {
      position: 2,
      city_id: 2,
      name: "Florence",
      country_iso2: "IT",
      lat: FLORENCE.lat,
      lon: FLORENCE.lon,
      days: 2,
    },
    {
      position: 1,
      city_id: 1,
      name: "Rome",
      country_iso2: "IT",
      lat: ROME.lat,
      lon: ROME.lon,
      days: 3,
    },
  ],
} as unknown as Trip;

const days = [
  { day_index: 1, base_city_name: "Rome", base_city_lat: ROME.lat, base_city_lon: ROME.lon },
  {
    day_index: 4,
    base_city_name: "Florence",
    base_city_lat: FLORENCE.lat,
    base_city_lon: FLORENCE.lon,
  },
] as unknown as Day[];

function sight(id: string, lat: number, lon: number, match: PlaceSummary["match"]): PlaceSummary {
  return {
    id,
    name: id,
    kind: "attraction",
    category: "church",
    lat,
    lon,
    region_id: "italy",
    match,
  } as PlaceSummary;
}

test("a straight-line distance", () => {
  expect(distanceMeters(ROME, FLORENCE) / 1000).toBeCloseTo(232, -1);
});

test("a multi-city trip searches around each of its cities, in the trip's order", () => {
  expect(tripAnchors(trip).map((a) => a.name)).toEqual(["Rome", "Florence"]);
  const single = {
    destination: { name: "Vienna", lat: 48.2, lon: 16.37 },
    stops: [],
  } as unknown as Trip;
  expect(tripAnchors(single)).toEqual([{ name: "Vienna", lat: 48.2, lon: 16.37 }]);
});

test("a day's city comes from its base city; with no day a multi-city trip has none", () => {
  expect(dayAnchor(trip, days, 4)?.name).toBe("Florence");
  expect(dayAnchor(trip, days, undefined)).toBeNull();
  expect(searchAnchors(tripAnchors(trip), dayAnchor(trip, days, 4)).map((a) => a.name)).toEqual([
    "Florence",
    "Rome",
  ]);
});

test("the day's city comes first and distances are measured from it", () => {
  const rome = sight("San Lorenzo fuori le Mura", 41.9024, 12.5214, "prefix");
  const florence = sight("Basilica di San Lorenzo", 43.7749, 11.2537, "contains");
  const merged = mergeSights(
    [
      { anchor: FLORENCE, results: [florence] },
      { anchor: ROME, results: [rome, florence] },
    ],
    FLORENCE,
  );
  expect(merged.map((s) => s.place.id)).toEqual([florence.id, rome.id]);
  expect(merged[0]?.from.name).toBe("Florence");
  expect(merged[0]?.meters).toBeLessThan(1_000);
  expect(merged[1]?.from.name).toBe("Florence");
});

test("with no day, each sight is measured from the nearest of the trip's cities", () => {
  const rome = sight("Pantheon", 41.8986, 12.4769, "exact");
  const florence = sight("Duomo", 43.7731, 11.256, "exact");
  const merged = mergeSights(
    [
      { anchor: ROME, results: [rome] },
      { anchor: FLORENCE, results: [florence] },
    ],
    null,
  );
  expect(merged.map((s) => [s.place.id, s.from.name])).toEqual([
    ["Duomo", "Florence"],
    ["Pantheon", "Rome"],
  ]);
});
