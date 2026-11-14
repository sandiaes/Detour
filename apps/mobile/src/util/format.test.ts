import {
  formatAge,
  formatClock,
  formatDate,
  formatMeters,
  formatMinutes,
  formatSeconds,
  formatTripSpan,
  isValidIsoDate,
} from "./format";

test("durations", () => {
  expect(formatMinutes(0)).toBe("0 min");
  expect(formatMinutes(45)).toBe("45 min");
  expect(formatMinutes(60)).toBe("1 h");
  expect(formatMinutes(90)).toBe("1 h 30 min");
  expect(formatSeconds(20)).toBe("1 min");
  expect(formatSeconds(1260)).toBe("21 min");
  expect(formatSeconds(61)).toBe("2 min");
});

test("distances", () => {
  expect(formatMeters(380)).toBe("380 m");
  expect(formatMeters(4)).toBe("10 m");
  expect(formatMeters(1500)).toBe("1.5 km");
  expect(formatMeters(42000)).toBe("42 km");
});

test("clock times and dates", () => {
  expect(formatClock("09:30:00")).toBe("09:30");
  expect(formatClock(null)).toBeNull();
  expect(formatDate("2027-05-01")).toBe("Sat 1 May 2027");
  expect(formatDate("2027-05-01", false)).toBe("Sat 1 May");
  expect(formatDate("not a date")).toBe("not a date");
  expect(formatTripSpan("2027-05-01", "2027-05-03", 3)).toBe(
    "Sat 1 May to Mon 3 May 2027 · 3 days",
  );
  expect(formatTripSpan(null, null, 1)).toBe("1 day");
});

test("date validation rejects impossible dates", () => {
  expect(isValidIsoDate("2027-02-28")).toBe(true);
  expect(isValidIsoDate("2028-02-29")).toBe(true);
  expect(isValidIsoDate("2027-02-29")).toBe(false);
  expect(isValidIsoDate("2027-13-01")).toBe(false);
  expect(isValidIsoDate("27-05-01")).toBe(false);
  expect(isValidIsoDate("")).toBe(false);
});

test("age of a saved copy", () => {
  const now = 10_000_000_000;
  expect(formatAge(now - 30_000, now)).toBe("just now");
  expect(formatAge(now - 5 * 60_000, now)).toBe("5 minutes ago");
  expect(formatAge(now - 60 * 60_000, now)).toBe("1 hour ago");
  expect(formatAge(now - 72 * 3_600_000, now)).toBe("3 days ago");
});
