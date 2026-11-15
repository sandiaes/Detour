import { VENUES, parseCoordinate, venueLabel } from "./restaurants";

test("typed coordinates are validated", () => {
  expect(parseCoordinate("48.2082", "lat")).toBe(48.2082);
  expect(parseCoordinate("16,3738", "lon")).toBe(16.3738);
  expect(parseCoordinate("-33.5", "lat")).toBe(-33.5);
  expect(parseCoordinate("91", "lat")).toBeNull();
  expect(parseCoordinate("181", "lon")).toBeNull();
  expect(parseCoordinate("abc", "lat")).toBeNull();
  expect(parseCoordinate("", "lon")).toBeNull();
});

test("a restaurant or café is only what Photon can say: its kind", () => {
  expect(VENUES).toEqual(["restaurant", "cafe"]);
  expect(venueLabel("cafe")).toBe("Café");
  expect(venueLabel("restaurant")).toBe("Restaurant");
  expect(venueLabel(null)).toBe("Restaurant or café");
  expect(venueLabel("bar")).toBe("Restaurant or café");
});
