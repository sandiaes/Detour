import { makeChangeSet } from "../testing/fixtures";
import { diffSections, diffSummary, travelChangeText } from "./changes";

test("travel change reads as a signed total", () => {
  expect(travelChangeText(18)).toBe("+18 min travel in total");
  expect(travelChangeText(-75)).toBe("−1 h 15 min travel in total");
  expect(travelChangeText(0)).toBe("No change in travel time");
});

test("sections follow the diff and flag what is left out", () => {
  const sections = diffSections(makeChangeSet().diff);
  expect(sections.map((s) => s.key)).toEqual(["added", "removed", "moved", "retimed", "estimated"]);
  expect(sections.find((s) => s.key === "removed")?.warn).toBe(true);
  expect(sections.find((s) => s.key === "retimed")?.title).toBe("New times (1 item)");
});

test("base changes and an unchanged plan", () => {
  const diff = {
    ...makeChangeSet().diff,
    added: [],
    removed: [],
    moved: [],
    retimed: [],
    estimated_legs: [],
    base_changes: [{ day: 3, old_base_name: "Vienna", new_base_name: "Melk" }],
  };
  expect(diffSections(diff)).toEqual([
    { key: "bases", title: "Base city", lines: ["Day 3: Vienna → Melk"] },
  ]);
  expect(diffSummary({ ...diff, days_changed: [] })).toBe("Nothing in the plan changes.");
  expect(diffSummary({ ...diff, days_changed: [3], travel_minutes_added: 0 })).toBe(
    "Day 3 changes · no change in travel time.",
  );
});
