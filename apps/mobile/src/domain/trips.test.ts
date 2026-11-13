import { makeArchiveInfo, makeItinerary, makePastTrip, makeTrip } from "../testing/fixtures";
import {
  countsFromArchive,
  countsFromItinerary,
  countsLine,
  countsWithoutPlan,
  localToday,
  shortSpan,
  tripPhase,
  tripsInTab,
} from "./trips";

describe("tripPhase", () => {
  test("no chosen plan is Planning, whatever the dates", () => {
    expect(tripPhase(makeTrip(), "2027-05-01")).toBe("planning");
  });
  test("a chosen plan before the first day is Upcoming", () => {
    expect(tripPhase(makeTrip({ selected_itinerary_id: "x" }), "2027-04-30")).toBe("upcoming");
  });
  test("a chosen plan during the dates is In progress", () => {
    const trip = makeTrip({ selected_itinerary_id: "x" });
    expect(tripPhase(trip, "2027-05-01")).toBe("inProgress");
    expect(tripPhase(trip, "2027-05-02")).toBe("inProgress");
  });
  test("the backend's past status wins (ADR 006)", () => {
    expect(tripPhase(makePastTrip(), "2027-05-01")).toBe("past");
  });
  test("a chosen plan without dates is Upcoming", () => {
    const trip = makeTrip({ selected_itinerary_id: "x", start_date: null, end_date: null });
    expect(tripPhase(trip, "2027-05-01")).toBe("upcoming");
  });
});

test("localToday is the device's local calendar date", () => {
  expect(localToday(new Date(2027, 0, 5, 23, 59))).toBe("2027-01-05");
});

describe("tripsInTab", () => {
  const later = makeTrip({ id: "b", start_date: "2027-06-01", end_date: "2027-06-02" });
  const sooner = makeTrip({ id: "a", start_date: "2027-05-01" });
  const undatedOld = makeTrip({
    id: "c",
    start_date: null,
    end_date: null,
    created_at: "2026-01-01T00:00:00Z",
  });
  const undatedNew = makeTrip({
    id: "d",
    start_date: null,
    end_date: null,
    created_at: "2026-06-01T00:00:00Z",
  });
  const pastOld = makePastTrip({ id: "p1", start_date: "2025-01-01" });
  const pastNew = makePastTrip({ id: "p2", start_date: "2026-01-01" });
  const all = [undatedOld, later, pastOld, sooner, pastNew, undatedNew];

  test("upcoming: soonest first, then undated trips, newest first", () => {
    expect(tripsInTab(all, "upcoming").map((t) => t.id)).toEqual(["a", "b", "d", "c"]);
  });
  test("past: most recent first", () => {
    expect(tripsInTab(all, "past").map((t) => t.id)).toEqual(["p2", "p1"]);
  });
  test("the input is not reordered", () => {
    const copy = [...all];
    tripsInTab(all, "upcoming");
    expect(all).toEqual(copy);
  });
});

describe("counts", () => {
  test("from the active plan: base cities, visits and meals at a place to eat", () => {
    const trip = makeTrip({ selected_itinerary_id: "x" });
    const counts = countsFromItinerary(trip, makeItinerary("essentials"));
    expect(counts.days).toBe(2);
    expect(counts.cities).toBe(2); // Vienna and Graz in the fixture
    expect(counts.places).toBeGreaterThan(0);
    expect(counts.restaurants).toBe(2);
  });

  test("a single-city plan with no base names counts the destination once", () => {
    const plan = makeItinerary("essentials");
    for (const d of plan.days) d.base_city_name = null;
    const counts = countsFromItinerary(makeTrip(), plan);
    expect(counts.cities).toBe(1);
  });

  test("an area plan with no base names leaves cities unknown, not zero", () => {
    const plan = makeItinerary("essentials");
    for (const d of plan.days) d.base_city_name = null;
    const trip = makeTrip({ destination: { ...makeTrip().destination, kind: "area" } });
    expect(countsFromItinerary(trip, plan).cities).toBeNull();
  });

  test("a past trip has cities and attractions, and no restaurant figure (ADR 006)", () => {
    expect(countsFromArchive(makePastTrip(), makeArchiveInfo())).toEqual({
      days: 4,
      cities: 2,
      places: 3,
      restaurants: null,
    });
  });

  test("without a plan only the days and a city destination are known", () => {
    expect(countsWithoutPlan(makeTrip())).toEqual({
      days: 2,
      cities: 1,
      places: null,
      restaurants: null,
    });
  });

  test("the line leaves out unknown figures and uses singulars", () => {
    expect(countsLine({ days: 1, cities: 1, places: 1, restaurants: null })).toBe(
      "1 city · 1 place",
    );
    expect(countsLine({ days: 3, cities: 2, places: 12, restaurants: 4 })).toBe(
      "2 cities · 12 places · 4 restaurants",
    );
    expect(countsLine({ days: 3, cities: null, places: null, restaurants: null })).toBeNull();
  });
});

describe("shortSpan", () => {
  test("within a month", () => {
    expect(shortSpan(makeTrip())).toBe("1–2 May 2027 · 2 days");
  });
  test("one day", () => {
    expect(
      shortSpan(makeTrip({ duration_days: 1, start_date: "2027-05-01", end_date: "2027-05-01" })),
    ).toBe("1 May 2027 · 1 day");
  });
  test("across months and years", () => {
    expect(
      shortSpan(makeTrip({ duration_days: 4, start_date: "2027-05-30", end_date: "2027-06-02" })),
    ).toBe("30 May – 2 Jun 2027 · 4 days");
    expect(
      shortSpan(makeTrip({ duration_days: 3, start_date: "2027-12-31", end_date: "2028-01-02" })),
    ).toBe("31 Dec 2027 – 2 Jan 2028 · 3 days");
  });
  test("without dates, the length only", () => {
    expect(shortSpan(makeTrip({ start_date: null, end_date: null, duration_days: 5 }))).toBe(
      "5 days",
    );
  });
});
