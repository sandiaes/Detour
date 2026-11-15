import type { TripVisit } from "@detour/shared";

import { formatBytes, formatDayLabel } from "../util/format";
import {
  dayRecord,
  groupVisitsByCity,
  stopRecordLine,
  visitCounts,
  visitedPoints,
} from "./pastTrip";

function visit(over: Partial<TripVisit> & Pick<TripVisit, "id" | "kind" | "name">): TripVisit {
  return {
    lat: 48.2,
    lon: 16.37,
    geo_place_ref: null,
    day_number: 1,
    position: null,
    start_time: null,
    duration_minutes: null,
    confirmed: true,
    ...over,
  };
}

const VIENNA = visit({ id: "c1", kind: "city", name: "Vienna" });
const GRAZ = visit({ id: "c2", kind: "city", name: "Graz", lat: 47.07, lon: 15.44, day_number: 3 });
const HOFBURG = visit({ id: "a1", kind: "attraction", name: "Hofburg", lat: 48.206, lon: 16.366 });
const SCHLOSSBERG = visit({
  id: "a2",
  kind: "attraction",
  name: "Schlossberg",
  lat: 47.0737,
  lon: 15.4375,
  day_number: 3,
});
const BELVEDERE = visit({
  id: "a3",
  kind: "attraction",
  name: "Belvedere",
  lat: 48.191,
  lon: 16.381,
  day_number: 2,
});

test("visits are grouped under the nearest city, each city once", () => {
  const groups = groupVisitsByCity([VIENNA, HOFBURG, BELVEDERE, GRAZ, SCHLOSSBERG], "Austria");
  expect(groups.map((g) => [g.name, g.visits.map((v) => v.name)])).toEqual([
    ["Vienna", ["Hofburg", "Belvedere"]],
    ["Graz", ["Schlossberg"]],
  ]);
});

test("a city without attractions is still a group", () => {
  const groups = groupVisitsByCity([VIENNA, GRAZ], "Austria");
  expect(groups.map((g) => [g.name, g.visits.length])).toEqual([
    ["Vienna", 0],
    ["Graz", 0],
  ]);
});

test("attractions with no city in the archive form one group named after the destination", () => {
  expect(groupVisitsByCity([HOFBURG, SCHLOSSBERG], "Styria")).toEqual([
    { key: "all", name: "Styria", city: null, visits: [HOFBURG, SCHLOSSBERG] },
  ]);
  expect(groupVisitsByCity([], "Styria")).toEqual([]);
});

test("a skipped visit is counted as skipped, not as visited, and has no marker", () => {
  const skipped = { ...HOFBURG, confirmed: false };
  const visits = [VIENNA, skipped, BELVEDERE, { ...GRAZ, confirmed: false }];
  expect(visitCounts(visits)).toEqual({ cities: 1, attractions: 1, placesToEat: 0, skipped: 2 });
  expect(visitedPoints(visits).map((p) => p.name)).toEqual(["Vienna", "Belvedere"]);
});

test("map points are [lon, lat] with cities first, and carry nothing about routes", () => {
  const points = visitedPoints([HOFBURG, VIENNA]);
  expect(points.map((p) => p.kind)).toEqual(["city", "attraction"]);
  expect(points[0]?.lngLat).toEqual([16.37, 48.2]);
  expect(Object.keys(points[0] ?? {}).sort()).toEqual(["day", "id", "kind", "lngLat", "name"]);
});

test("day labels use the start date when there is one", () => {
  expect(formatDayLabel("2027-05-01", 2)).toBe("Day 2 · Sun 2 May");
  expect(formatDayLabel(null, 2)).toBe("Day 2");
});

test("sizes are written in plain units", () => {
  expect(formatBytes(1)).toBe("1 byte");
  expect(formatBytes(812)).toBe("812 bytes");
  expect(formatBytes(4519)).toBe("4.5 kB");
  expect(formatBytes(1_250_000)).toBe("1.3 MB");
});

test("the day record lists each day's stops in their planned order, restaurants and cafés too", () => {
  const cafe = visit({
    id: "e1",
    kind: "cafe",
    name: "Café Central",
    position: 2,
    start_time: "11:00",
    duration_minutes: 45,
  });
  const first = visit({
    id: "a9",
    kind: "attraction",
    name: "Zoo",
    position: 1,
    start_time: "09:30",
  });
  const older = visit({ id: "a8", kind: "attraction", name: "Alt", day_number: 2 });
  const second = visit({ id: "a7", kind: "attraction", name: "Boot", day_number: 2, position: 1 });
  const record = dayRecord([VIENNA, cafe, older, first, second]);
  expect(record.map((d) => [d.day, d.stops.map((s) => s.name)])).toEqual([
    [1, ["Zoo", "Café Central"]],
    [2, ["Boot", "Alt"]], // no order: after the ordered ones
  ]);
  expect(stopRecordLine(cafe)).toBe("Café · 11:00 · 45 min");
  expect(stopRecordLine(older)).toBe("Attraction");
});

test("places to eat are counted apart and group under the nearest city", () => {
  const eat = visit({ id: "e2", kind: "restaurant", name: "Gasthaus", lat: 48.2, lon: 16.37 });
  expect(visitCounts([VIENNA, HOFBURG, eat])).toEqual({
    cities: 1,
    attractions: 1,
    placesToEat: 1,
    skipped: 0,
  });
  expect(groupVisitsByCity([VIENNA, eat], "x")[0]?.visits.map((v) => v.name)).toEqual(["Gasthaus"]);
});
