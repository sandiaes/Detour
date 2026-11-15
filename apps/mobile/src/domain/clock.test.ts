import { clockFrom, hoursText, minutesFromHours, parseClock } from "./clock";

test("parseClock accepts a time of day and nothing else", () => {
  expect(parseClock("9:30")).toBe("09:30");
  expect(parseClock("14.05")).toBe("14:05");
  expect(parseClock("24:00")).toBeNull();
  expect(parseClock("soon")).toBeNull();
});

test("clockFrom wraps round midnight in both directions", () => {
  expect(clockFrom(23, 60)).toBe("00:00");
  expect(clockFrom(0, -5)).toBe("23:55");
  expect(clockFrom(9, 30)).toBe("09:30");
});

test("hours are typed with a dot or a comma and shown without trailing zeros", () => {
  expect(minutesFromHours("1.5")).toBe(90);
  expect(minutesFromHours("1,25")).toBe(75);
  expect(minutesFromHours("abc")).toBeNull();
  expect(minutesFromHours("0")).toBeNull();
  expect(hoursText(90)).toBe("1.5");
  expect(hoursText(120)).toBe("2");
});
