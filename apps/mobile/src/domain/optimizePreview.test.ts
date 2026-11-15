import { makeItinerary } from "../testing/fixtures";
import { formatDistance, proposedDays, travelMeters } from "./optimize";

const days = makeItinerary("essentials").days;
const first = days[0]!;

test("the proposed order replaces a day's order, times and travel", () => {
  const [a, b] = first.items;
  const proposed = proposedDays(days, {
    stops: [
      {
        item_id: b!.id,
        day_index: first.day_index,
        position: 0,
        start_time: "09:00:00",
        end_time: "10:00:00",
      },
      {
        item_id: a!.id,
        day_index: first.day_index,
        position: 1,
        start_time: "10:20:00",
        end_time: "11:20:00",
      },
    ],
    transfers: [
      {
        from_item_id: b!.id,
        to_item_id: a!.id,
        mode: "walk",
        seconds: 600,
        meters: 700,
        confidence: "routed",
      },
    ],
  });
  const day = proposed.find((d) => d.day_index === first.day_index)!;
  expect(day.items.map((i) => i.id)).toEqual([b!.id, a!.id]);
  expect(day.items[0]!.transfer?.to_item_id).toBe(a!.id);
  expect(day.items[1]!.transfer).toBeNull();
  expect(day.items[1]!.start_time).toBe("10:20:00");
  expect(travelMeters(proposed)).toBe(700);
  // The current plan is untouched.
  expect(first.items.length).toBeGreaterThan(2);
});

test("distances read in words", () => {
  expect(formatDistance(850)).toBe("850 m");
  expect(formatDistance(2340)).toBe("2.3 km");
  expect(formatDistance(14200)).toBe("14 km");
});
