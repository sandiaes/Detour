import type { SlotSuggestion } from "@detour/shared";

import {
  detourText,
  formatMealTypes,
  movedLines,
  parseCoordinate,
  parseCuisines,
  restaurantMeta,
  suggestionPlace,
  suggestionTitle,
} from "./restaurants";

const slot: SlotSuggestion = {
  rank: 1,
  day: 2,
  meal_type: "lunch",
  start_time: "12:15:00",
  end_time: "13:15:00",
  after_item_id: "a",
  after_name: "Belvedere",
  before_name: "Albertina",
  travel_minutes_added: 6,
  travel_label: "estimated",
  detour_metres: 340,
  replaces: null,
  items_moved: [],
  reasons: [],
  score: 120,
};

test("cuisines are typed freely and stored as the open data stores them", () => {
  expect(parseCuisines("Italian, pizza ; Sushi bar, italian")).toEqual([
    "italian",
    "pizza",
    "sushi_bar",
  ]);
  // Nothing typed is "not specified", never an empty list.
  expect(parseCuisines("")).toBeUndefined();
  expect(parseCuisines(" , ; ")).toBeUndefined();
});

test("typed coordinates are validated", () => {
  expect(parseCoordinate("48.2082", "lat")).toBe(48.2082);
  expect(parseCoordinate("16,3738", "lon")).toBe(16.3738);
  expect(parseCoordinate("-33.5", "lat")).toBe(-33.5);
  expect(parseCoordinate("91", "lat")).toBeNull();
  expect(parseCoordinate("181", "lon")).toBeNull();
  expect(parseCoordinate("abc", "lat")).toBeNull();
  expect(parseCoordinate("", "lon")).toBeNull();
});

test("what the data does not state is said so", () => {
  expect(formatMealTypes(null)).toBe("Meals not specified");
  expect(formatMealTypes(["dinner", "lunch"])).toBe("Lunch, Dinner");
  expect(restaurantMeta({ cuisines: null, venue_type: "cafe", meal_types: ["snack"] })).toBe(
    "Cuisine not specified · Café · Afternoon snack",
  );
  expect(
    restaurantMeta({
      cuisines: ["austrian", "regional"],
      venue_type: "restaurant",
      meal_types: ["dinner", "lunch"],
      city_name: "Vienna",
    }),
  ).toBe("Austrian, regional · Restaurant · Lunch, Dinner · Vienna");
});

test("a suggestion reads as day, meal, time, neighbours, detour and moved items", () => {
  expect(suggestionTitle(slot)).toBe("Day 2 · Lunch · 12:15–13:15");
  expect(suggestionPlace(slot)).toBe("Between Belvedere and Albertina");
  expect(suggestionPlace({ ...slot, before_name: null })).toBe(
    "After Belvedere, the last stop of the day",
  );
  expect(detourText(slot)).toBe("+6 min travel that day (estimated)");
  expect(detourText({ ...slot, travel_minutes_added: 0, travel_label: "routed" })).toBe(
    "No extra travel (routed)",
  );
  expect(movedLines(slot)).toEqual(["No other item moves."]);
  expect(
    movedLines({
      ...slot,
      items_moved: [
        {
          kind: "visit",
          name: "Albertina",
          old_start_time: "13:00:00",
          new_start_time: "13:40:00",
        },
      ],
    }),
  ).toEqual(["1 other item starts at another time:", "Albertina 13:00 → 13:40"]);
});
