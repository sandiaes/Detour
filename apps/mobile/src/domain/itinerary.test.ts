import type { Day } from "@detour/shared";

import { stopSummary } from "../components/plan/DayPlan";
import { makeItinerary } from "../testing/fixtures";
import {
  boundsOf,
  buildDayRows,
  dayTotals,
  mapPoints,
  transferFeatures,
  transportFeature,
  transportPoint,
} from "./itinerary";

const day1 = makeItinerary("essentials").days[0]!;

test("rows alternate items and the transfer that follows them", () => {
  const rows = buildDayRows(day1);
  expect(rows.map((r) => r.kind)).toEqual([
    "item",
    "transfer",
    "item",
    "transfer",
    "item",
    "transfer",
    "item",
    "transfer",
    "item",
  ]);
  expect(
    rows.filter((r) => r.kind === "item").map((r) => (r.kind === "item" ? r.ordinal : 0)),
  ).toEqual([1, 2, 3, 4, 5]);
  const transfer = rows[1]!;
  expect(transfer.kind === "transfer" && transfer.to?.display_name).toBe("Belvedere");
});

test("items without a place are not numbered", () => {
  const day = structuredClone(day1);
  day.items[1]!.lat = null;
  day.items[1]!.lon = null;
  const ordinals = buildDayRows(day).flatMap((r) => (r.kind === "item" ? [r.ordinal] : []));
  expect(ordinals).toEqual([1, null, 2, 3, 4]);
});

test("totals add visit minutes and transfer seconds, and count meals", () => {
  expect(dayTotals(day1)).toEqual({
    visits: 3,
    meals: 2,
    visitMinutes: 270,
    travelSeconds: 1260 + 600 + 120 + 240,
  });
});

test("the drive from the previous base city counts as travel", () => {
  const day2 = makeItinerary("essentials").days[1]!;
  expect(dayTotals(day2)).toEqual({
    visits: 2,
    meals: 0,
    visitMinutes: 180,
    travelSeconds: 8400 + 300,
  });
});

test("map points are numbered like the list, and lines carry the label of the time", () => {
  const points = mapPoints(day1);
  expect(points.map((p) => [p.ordinal, p.name])).toEqual([
    [1, "Schönbrunn Palace"],
    [2, "Belvedere"],
    [3, "Gasthaus Zum Test"],
    [4, "St. Stephen's Cathedral"],
    [5, "Café Ohne Angabe"],
  ]);
  const lines = transferFeatures(day1);
  expect(lines.map((l) => [l.properties.confidence, l.properties.mode])).toEqual([
    ["estimated", "walk"],
    ["routed", "drive"],
    ["estimated", "walk"],
    ["estimated", "walk"],
  ]);
  expect(lines[0]!.geometry.coordinates).toEqual([points[0]!.lngLat, points[1]!.lngLat]);
});

test("bounds", () => {
  expect(boundsOf([])).toBeNull();
  const b = boundsOf(mapPoints(day1))!;
  expect(b[0]).toBeCloseTo(16.3122);
  expect(b[1]).toBeCloseTo(48.1845);
  expect(b[2]).toBeCloseTo(16.3808);
  expect(b[3]).toBeCloseTo(48.2091);
});

describe("transport points (ADR 021)", () => {
  const plan = makeItinerary("essentials");
  const [d1, d2] = plan.days as [Day, Day];

  test("a day that starts at a new base city has a transport point at that city", () => {
    const point = transportPoint(d2, d1);
    expect(point).toMatchObject({
      id: `arrival-${d2.id}`,
      name: "Graz",
      fromName: "Vienna",
      lngLat: [15.4395, 47.0707],
      fromLngLat: [16.3738, 48.2082],
    });
    expect(transportFeature(point!)?.geometry.coordinates).toEqual([
      [16.3738, 48.2082],
      [15.4395, 47.0707],
    ]);
  });

  test("no arrival, or no known position, means no point", () => {
    expect(transportPoint(d1, undefined)).toBeNull();
    expect(transportPoint({ ...d2, base_city_lat: null }, d1)).toBeNull();
  });

  test("without the previous city's position the point stands alone, with no line", () => {
    const point = transportPoint(d2, { ...d1, base_city_lon: null });
    expect(point?.fromLngLat).toBeNull();
    expect(transportFeature(point!)).toBeNull();
  });
});

test("stopSummary says what a stop is and how long it lasts", () => {
  const [d1] = makeItinerary("essentials").days as [Day];
  expect(d1.items.map(stopSummary)).toEqual([
    "Attraction · 2 h",
    "Attraction · 1 h 30 min",
    "Restaurant · 1 h",
    "Attraction · 1 h",
    "Café · 1 h 30 min",
  ]);
});
