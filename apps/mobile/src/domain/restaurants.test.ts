import { formatMealTypes, parseCoordinate, parseCuisines, restaurantMeta } from "./restaurants";

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
