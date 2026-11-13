import type { ChangeDiff } from "@detour/shared";

import { formatClock, formatMinutes, pluralise } from "../util/format";

// How a previewed change reads in the app (Phase 7, ADR 018). Everything here is the server's
// diff rearranged; nothing is computed that the server did not say.

export type DiffSection = {
  key: "added" | "removed" | "moved" | "bases" | "retimed" | "estimated";
  title: string;
  /** Left out of the plan: shown with a warning so nothing disappears unnoticed. */
  warn?: boolean;
  lines: string[];
};

const MEAL: Record<string, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  snack: "Afternoon snack",
  dinner: "Dinner",
};

function what(kind: string, name: string, meal: string | null | undefined): string {
  return kind === "meal" && meal ? `${MEAL[meal] ?? "Meal"} at ${name}` : name;
}

const clock = (t: string) => formatClock(t) ?? t;

/** "+25 min travel", "−10 min travel" or "No change in travel time". */
export function travelChangeText(minutes: number): string {
  if (minutes === 0) return "No change in travel time";
  const sign = minutes > 0 ? "+" : "−";
  return `${sign}${formatMinutes(Math.abs(minutes))} travel in total`;
}

export function diffSections(diff: ChangeDiff): DiffSection[] {
  const sections: DiffSection[] = [];
  if (diff.added.length) {
    sections.push({
      key: "added",
      title: "Added",
      lines: diff.added.map(
        (a) =>
          `Day ${a.day}, ${clock(a.start_time)}: ${what(a.kind, a.name, a.meal_type)}` +
          (a.added_by_you ? " (your addition)" : ""),
      ),
    });
  }
  if (diff.removed.length) {
    sections.push({
      key: "removed",
      title: "Left out of the plan",
      warn: true,
      lines: diff.removed.map(
        (r) => `Day ${r.day}, ${clock(r.start_time)}: ${what(r.kind, r.name, r.meal_type)}`,
      ),
    });
  }
  if (diff.moved.length) {
    sections.push({
      key: "moved",
      title: "Moved to another day",
      lines: diff.moved.map(
        (m) =>
          `${m.name}: day ${m.from_day} ${clock(m.old_start_time)} → day ${m.to_day} ${clock(m.new_start_time)}`,
      ),
    });
  }
  if (diff.base_changes.length) {
    sections.push({
      key: "bases",
      title: "Base city",
      lines: diff.base_changes.map(
        (b) => `Day ${b.day}: ${b.old_base_name ?? "no base"} → ${b.new_base_name ?? "no base"}`,
      ),
    });
  }
  if (diff.retimed.length) {
    sections.push({
      key: "retimed",
      title: `New times (${pluralise(diff.retimed.length, "item")})`,
      lines: diff.retimed.map(
        (r) =>
          `Day ${r.day}: ${what(r.kind, r.name, r.meal_type)} ${clock(r.old_start_time)} → ${clock(r.new_start_time)}`,
      ),
    });
  }
  if (diff.estimated_legs.length) {
    sections.push({
      key: "estimated",
      title: "Estimated travel times",
      lines: diff.estimated_legs.map(
        (l) =>
          `Day ${l.day}: ${l.mode === "walk" ? "walk" : "drive"} ${l.from_name} → ${l.to_name}, about ${formatMinutes(l.minutes)}`,
      ),
    });
  }
  return sections;
}

/** One sentence for screen readers and the top of the preview. */
export function diffSummary(diff: ChangeDiff): string {
  const parts: string[] = [];
  if (diff.days_changed.length === 0) return "Nothing in the plan changes.";
  parts.push(
    diff.days_changed.length === 1
      ? `Day ${diff.days_changed[0]} changes`
      : `Days ${diff.days_changed.join(", ")} change`,
  );
  if (diff.removed.length) parts.push(`${pluralise(diff.removed.length, "item")} left out`);
  if (diff.moved.length) parts.push(`${pluralise(diff.moved.length, "visit")} moved`);
  parts.push(travelChangeText(diff.travel_minutes_added).toLowerCase());
  return `${parts.join(" · ")}.`;
}
