import type { Day, Item } from "@detour/shared";

import { makeItinerary, makeLeg } from "../testing/fixtures";
import { buildDayRows, dayTotals } from "./itinerary";
import {
  journeyLeg,
  legClash,
  legLine,
  legPosition,
  legSentence,
  legTimes,
  legsOnMap,
} from "./transport";

// Transport legs the user entered (ADR 032): what the day list says, what the map draws, and what
// counts as travel. A length the user did not enter is never guessed.

const dayWith = (items: Item[], over: Partial<Day> = {}): Day => {
  const day = makeItinerary("essentials").days[0] as Day;
  return { ...day, items, ...over };
};

test("a leg reads as its mode, its length and its times", () => {
  expect(legLine(makeLeg())).toBe("Train · 1 h 30 min · 10:12 to 11:42");
  expect(legSentence(makeLeg())).toMatch(
    /^Train from Rome to Florence\. 1 h 30 min\. 10:12 to 11:42\./,
  );
  expect(legSentence(makeLeg())).toMatch(/Entered by you\.$/);
});

test("a length not entered is said to be unknown, never guessed", () => {
  const leg = makeLeg({ duration_minutes: null, end_time: null });
  expect(legLine(leg)).toBe("Train · time not entered · from 10:12");
  expect(legSentence(leg)).toContain("Length not entered");
  const untimed = makeLeg({ duration_minutes: null, end_time: null, start_time: null });
  expect(legLine(untimed)).toBe("Train · time not entered");
});

test("a night train arrives the next day", () => {
  const night = makeLeg({ start_time: "22:30:00", end_time: null, duration_minutes: 520 });
  expect(legTimes(night)).toBe("22:30 to 07:10 the next day");
});

test("a leg is its own row in the day, not a numbered stop", () => {
  const [a, b] = makeItinerary("essentials").days[0]!.items as Item[];
  const rows = buildDayRows(
    dayWith([{ ...a!, transfer: null }, makeLeg(), { ...b!, transfer: null }]),
  );
  expect(rows.map((r) => r.kind)).toEqual(["item", "leg", "item"]);
  const ordinals = rows.flatMap((r) => (r.kind === "item" ? [r.ordinal] : []));
  expect(ordinals).toEqual([1, 2]);
});

test("a leg's length counts as travel; one of unknown length adds nothing", () => {
  const known = dayTotals(dayWith([makeLeg()]));
  expect(known.travelSeconds).toBe(90 * 60);
  const unknown = dayTotals(dayWith([makeLeg({ duration_minutes: null, end_time: null })]));
  expect(unknown.travelSeconds).toBe(0);
});

test("a journey leg takes the computed arrival's place, in the totals too", () => {
  const plan = makeItinerary("essentials");
  const day2 = plan.days[1] as Day;
  const leg = makeLeg({ id: "j0" }, { is_journey: true });
  const covered: Day = {
    ...day2,
    arrival: { ...day2.arrival!, covered_by_item_id: "j0" },
    items: [leg, ...day2.items],
  };
  expect(journeyLeg(covered)?.id).toBe("j0");
  expect(dayTotals(covered).travelSeconds).toBe(90 * 60 + 300);
  expect(journeyLeg(day2)).toBeNull();
});

test("on the map a leg is a line between its ends; a typed end borrows the next stop", () => {
  const [a, b] = makeItinerary("essentials").days[0]!.items as Item[];
  const both = legsOnMap(dayWith([makeLeg()]));
  expect(both[0]!.line).toEqual([
    [12.5, 41.9],
    [11.25, 43.77],
  ]);
  const typedTo = legsOnMap(
    dayWith([a!, makeLeg({}, { to_name: "Firenze SMN", to_lat: null, to_lon: null }), b!]),
  );
  expect(typedTo[0]!.line).toEqual([
    [12.5, 41.9],
    [b!.lon, b!.lat],
  ]);
  const nothing = legsOnMap(
    dayWith([makeLeg({}, { from_lat: null, from_lon: null, to_lat: null, to_lon: null })]),
  );
  expect(nothing).toEqual([]);
});

// Placement and times (owner, 2026-11-16). Day 1 of the fixture: Schönbrunn 09:00-11:00,
// Belvedere 11:21-12:51, Gasthaus 13:01-14:01, St. Stephen's 14:03-15:03, Café 18:30-20:00.
const day1 = () => makeItinerary("essentials").days[0] as Day;
const schoen = { name: "Schönbrunn Palace", lat: 48.1845, lon: 16.3122 };

test("a leg from a stop of the day goes right after that stop", () => {
  expect(legPosition(day1(), { from: schoen, start: "16:00", journey: false })).toBe(2);
});

test("otherwise a journey goes first, then time order, then the end", () => {
  const typed = { name: "Wien Hbf", lat: null, lon: null };
  expect(legPosition(day1(), { from: typed, start: "16:00", journey: true })).toBe(1);
  expect(legPosition(day1(), { from: typed, start: "16:00", journey: false })).toBe(5);
  expect(legPosition(day1(), { from: typed, start: null, journey: false })).toBe(6);
  expect(legPosition(day1(), { from: null, start: "08:00", journey: false })).toBe(1);
});

test("the leg itself is left out when it is placed again", () => {
  const day = day1();
  day.items.splice(1, 0, makeLeg({ id: "leg1" }));
  expect(legPosition(day, { from: schoen, start: null, journey: false }, "leg1")).toBe(2);
});

test("a leg that runs into the next stop asks to move the later stops by the overlap", () => {
  // After Schönbrunn (ends 11:00), a 45 min bus at 11:00 ends 11:45; Belvedere starts 11:21.
  const clash = legClash(day1(), 2, { start: "11:00", minutes: 45 });
  expect(clash).toEqual({
    kind: "later",
    name: "Belvedere",
    start: "11:21",
    minutes: 24,
    count: 4,
  });
  expect(legClash(day1(), 2, { start: "11:00", minutes: 20 })).toEqual({ kind: "none" });
});

test("a leg that leaves before the stop before it ends is named, not fixed", () => {
  expect(legClash(day1(), 2, { start: "10:30", minutes: 20 })).toEqual({
    kind: "earlier",
    name: "Schönbrunn Palace",
    end: "11:00",
  });
});

test("moving the later stops past midnight is refused", () => {
  const clash = legClash(day1(), 5, { start: "18:00", minutes: 300 });
  expect(clash).toMatchObject({ kind: "midnight", name: "Café Ohne Angabe" });
});

test("a leg with no time, or of unknown length at a free moment, clashes with nothing", () => {
  expect(legClash(day1(), 2, { start: null, minutes: 60 })).toEqual({ kind: "none" });
  expect(legClash(day1(), 2, { start: "11:10", minutes: null })).toEqual({ kind: "none" });
});
