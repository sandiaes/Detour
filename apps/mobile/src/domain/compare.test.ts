import { makeSummary } from "../testing/fixtures";
import { buildComparison, planFacts } from "./compare";

test("the summary lists the measured differences in fixed wording", () => {
  const c = buildComparison(makeSummary("essentials"), makeSummary("wider"));
  expect(c.rows.map((r) => r.label)).toEqual([
    "Visits",
    "Days with visits",
    "Meals",
    "Time at the sights",
    "Travel time",
    "Transfers",
  ]);
  expect(c.rows[0]).toMatchObject({ a: "5", b: "8" });
  expect(c.rows[2]).toMatchObject({ a: "1", b: "3" });
  expect(c.rows[3]).toMatchObject({ a: "7 h", b: "10 h" });
  expect(c.rows[4]).toMatchObject({ a: "40 min", b: "1 h 35 min" });
  expect(c.rows[5]).toMatchObject({ a: "1 routed, 2 estimated", b: "3 routed, 4 estimated" });
  expect(c.differences).toEqual([
    "Wider has 3 visits more than Essentials.",
    "Wider spends 55 min more travelling than Essentials.",
    "Wider plans 3 h more at the sights than Essentials.",
    "About 40 % of the visits are in both plans.",
  ]);
  expect(c.sharedPercent).toBe(40);
});

test("a missing statistic is shown as not available, never as zero", () => {
  const c = buildComparison(
    makeSummary("essentials", { stats: null, diversity_score: null }),
    makeSummary("wider", { diversity_score: null }),
  );
  expect(c.rows[0]).toMatchObject({ a: "Not available", b: "8" });
  expect(c.differences).toEqual([]);
  expect(c.sharedPercent).toBeNull();
});

test("identical numbers produce no difference sentence for them", () => {
  const a = makeSummary("essentials", { diversity_score: 0 });
  const c = buildComparison(a, { ...a, id: "other", profile: "wider" });
  expect(c.differences).toEqual(["The two plans have no visit in common."]);
});

test("facts of one plan", () => {
  expect(planFacts(makeSummary("essentials"))).toEqual([
    "5 visits",
    "40 min travelling",
    "7 h at the sights",
  ]);
  expect(planFacts(makeSummary("essentials", { stats: null }))).toEqual([]);
});
