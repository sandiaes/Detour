import { makeItinerary } from "../testing/fixtures";
import { boundsOf, buildDayRows, dayTotals, mapPoints, transferFeatures } from "./itinerary";

const day1 = makeItinerary("essentials").days[0]!;

test("rows alternate items and the transfer that follows them", () => {
  const rows = buildDayRows(day1);
  expect(rows.map((r) => r.kind)).toEqual(["item", "transfer", "item", "transfer", "item"]);
  expect(
    rows.filter((r) => r.kind === "item").map((r) => (r.kind === "item" ? r.ordinal : 0)),
  ).toEqual([1, 2, 3]);
  const transfer = rows[1]!;
  expect(transfer.kind === "transfer" && transfer.to?.display_name).toBe("Belvedere");
});

test("items without a place are not numbered", () => {
  const day = structuredClone(day1);
  day.items[1]!.lat = null;
  day.items[1]!.lon = null;
  const ordinals = buildDayRows(day).flatMap((r) => (r.kind === "item" ? [r.ordinal] : []));
  expect(ordinals).toEqual([1, null, 2]);
});

test("totals add visit minutes and transfer seconds", () => {
  expect(dayTotals(day1)).toEqual({ visits: 3, visitMinutes: 270, travelSeconds: 1860 });
});

test("map points are numbered like the list, and lines carry the label of the time", () => {
  const points = mapPoints(day1);
  expect(points.map((p) => [p.ordinal, p.name])).toEqual([
    [1, "Schönbrunn Palace"],
    [2, "Belvedere"],
    [3, "St. Stephen's Cathedral"],
  ]);
  const lines = transferFeatures(day1);
  expect(lines.map((l) => [l.properties.confidence, l.properties.mode])).toEqual([
    ["estimated", "walk"],
    ["routed", "drive"],
  ]);
  expect(lines[0]!.geometry.coordinates).toEqual([points[0]!.lngLat, points[1]!.lngLat]);
});

test("bounds", () => {
  expect(boundsOf([])).toBeNull();
  const b = boundsOf(mapPoints(day1))!;
  expect(b[0]).toBeCloseTo(16.3122);
  expect(b[1]).toBeCloseTo(48.1845);
  expect(b[2]).toBeCloseTo(16.3808);
  expect(b[3]).toBeCloseTo(48.2085);
});
