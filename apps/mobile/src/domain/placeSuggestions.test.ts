import { makePlaceSuggestions } from "../testing/fixtures";
import {
  affectedLines,
  placeSuggestionSentence,
  placeSuggestionTitle,
  placeSuggestionWhere,
  travelImpact,
} from "./placeSuggestions";

const [best, other] = makePlaceSuggestions().suggestions as [
  ReturnType<typeof makePlaceSuggestions>["suggestions"][number],
  ReturnType<typeof makePlaceSuggestions>["suggestions"][number],
];

test("title and place in the day", () => {
  expect(placeSuggestionTitle(best)).toBe("Day 1 · 15:10–17:10");
  expect(placeSuggestionWhere(best)).toBe("Between St. Stephen's Cathedral and Café Ohne Angabe");
  expect(placeSuggestionWhere(other)).toBe("Before Hofburg, the first stop of the day");
  expect(placeSuggestionWhere({ ...best, before_name: null })).toBe(
    "After St. Stephen's Cathedral, the last stop of the day",
  );
  expect(placeSuggestionWhere({ ...best, before_name: null, after_name: null })).toBe(
    "On its own in the day",
  );
});

test("travel impact is labelled routed or estimated, in both directions", () => {
  expect(travelImpact(12, true)).toBe("+12 min travel (estimated)");
  expect(travelImpact(-75, false)).toBe("1 h 15 min less travel (routed)");
  expect(travelImpact(0, true)).toBe("No extra travel (estimated)");
});

test("what else changes: left out first, as a warning", () => {
  expect(affectedLines(other.diff)).toEqual([
    { tone: "warn", text: "Leaves out Kunsthaus (day 2)" },
    { tone: "info", text: "Belvedere moves from day 1 to day 2" },
  ]);
  expect(affectedLines(best.diff)).toEqual([
    { tone: "info", text: "Café Ohne Angabe: 18:30 → 19:00" },
  ]);
  expect(
    affectedLines({
      ...best.diff,
      retimed: [],
      base_changes: [{ day: 3, old_base_name: "Vienna", new_base_name: "Melk" }],
    }),
  ).toEqual([{ tone: "info", text: "Day 3 is based in Melk instead of Vienna" }]);
});

test("one sentence for a screen reader", () => {
  expect(placeSuggestionSentence(other)).toBe(
    "Option 2: Day 2 · 10:05–12:05. Before Hofburg, the first stop of the day. +35 min travel " +
      "(routed). Leaves out Kunsthaus (day 2). Belvedere moves from day 1 to day 2",
  );
  expect(placeSuggestionSentence({ ...best, diff: { ...best.diff, retimed: [] } })).toMatch(
    /Nothing else changes$/,
  );
});
