import type { Day, Item } from "@detour/shared";

import { checkDuration, firstAvailableTime, parseMinutes } from "./duration";

function item(id: string, start: string | null, minutes: number, extra: Partial<Item> = {}): Item {
  return {
    id,
    type: "visit",
    display_name: id,
    start_time: start,
    end_time: null,
    duration_minutes: minutes,
    transfer: null,
    ...extra,
  } as Item;
}
const dayOf = (...items: Item[]) => ({ items }) as unknown as Day;

test("parses the lengths people type", () => {
  expect(parseMinutes("90")).toBe(90);
  expect(parseMinutes("45 min")).toBe(45);
  expect(parseMinutes("1:30")).toBe(90);
  expect(parseMinutes("1h30")).toBe(90);
  expect(parseMinutes("2 h")).toBe(120);
  expect(parseMinutes("1 h 15 min")).toBe(75);
  expect(parseMinutes("0")).toBeNull();
  expect(parseMinutes("")).toBeNull();
  expect(parseMinutes("abc")).toBeNull();
  expect(parseMinutes("1441")).toBeNull();
});

test("a length that runs into the next stop is an error", () => {
  const a = item("a", "10:00:00", 60);
  const b = item("b", "11:30:00", 30);
  expect(checkDuration(dayOf(a, b), a, 90)).toBeNull();
  expect(checkDuration(dayOf(a, b), a, 120)?.level).toBe("error");
});

test("too little time for the trip to the next stop is a warning", () => {
  const b = item("b", "11:30:00", 30);
  const a = item("a", "10:00:00", 60, {
    transfer: { to_item_id: "b", mode: "walk", seconds: 900, meters: 1000, confidence: "routed" },
  });
  expect(checkDuration(dayOf(a, b), a, 75)).toBeNull();
  const w = checkDuration(dayOf(a, b), a, 80);
  expect(w?.level).toBe("warning");
  expect(w?.text).toContain("15 min");
});

test("ending after the usual end of the day is a warning; an untimed stop never conflicts", () => {
  const late = item("late", "19:00:00", 30);
  expect(checkDuration(dayOf(late), late, 90)?.level).toBe("warning");
  const untimed = item("u", null, 30);
  expect(checkDuration(dayOf(untimed), untimed, 500)).toBeNull();
});

test("the suggested time of a day: the start of the day, or right after its last stop", () => {
  const timed = (id: string, start: string, end: string, travel = 0) =>
    item(id, start, 0, {
      end_time: end,
      transfer: travel ? ({ seconds: travel * 60 } as Item["transfer"]) : null,
    });
  expect(firstAvailableTime(undefined, 60)).toBe("09:00");
  expect(firstAvailableTime(dayOf(), 60)).toBe("09:00");
  // A gap before the first stop is not used: the new stop goes after the last one.
  expect(firstAvailableTime(dayOf(timed("a", "11:00", "12:00")), 60)).toBe("12:00");
  // After the last stop and the trip from it (10 minutes).
  expect(firstAvailableTime(dayOf(timed("a", "09:30", "11:00", 10)), 60)).toBe("11:10");
  // The last stop in time, wherever the list puts it.
  expect(
    firstAvailableTime(
      dayOf(
        timed("c", "15:00", "16:00"),
        timed("a", "09:00", "10:00"),
        timed("b", "10:30", "12:00"),
      ),
      90,
    ),
  ).toBe("16:00");
  // Free time is not a stop; a stop with no time is ignored; the moved stop does not block itself.
  expect(
    firstAvailableTime(
      dayOf(item("f", "09:00", 90, { type: "free_time", end_time: "10:30" }), item("n", null, 30)),
      60,
    ),
  ).toBe("09:00");
  expect(firstAvailableTime(dayOf(timed("a", "09:00", "10:00")), 60, "a")).toBe("09:00");
});
