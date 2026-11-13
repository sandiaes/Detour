import type { ChangeDiff, PlaceSuggestion } from "@detour/shared";

import { formatClock, formatMinutes } from "../util/format";
import { MEAL_LABEL } from "./restaurants";

// How a suggested day for a place reads (ADR 021, step 4). The days, times, travel and the items
// that move come from the server's recalculation; nothing here scores or decides anything.

const clock = (t: string) => formatClock(t) ?? t;

/** "Day 2 · 10:15–11:45". */
export function placeSuggestionTitle(s: PlaceSuggestion): string {
  return `Day ${s.day} · ${clock(s.start_time)}–${clock(s.end_time)}`;
}

/** Where it sits between the day's stops. */
export function placeSuggestionWhere(s: PlaceSuggestion): string {
  if (s.after_name && s.before_name) return `Between ${s.after_name} and ${s.before_name}`;
  if (s.after_name) return `After ${s.after_name}, the last stop of the day`;
  if (s.before_name) return `Before ${s.before_name}, the first stop of the day`;
  return "On its own in the day";
}

/** The travel it adds to the plan, labelled estimated when any changed leg is an estimate. */
export function travelImpact(minutes: number, estimated: boolean): string {
  const label = estimated ? "estimated" : "routed";
  if (minutes === 0) return `No extra travel (${label})`;
  if (minutes > 0) return `+${formatMinutes(minutes)} travel (${label})`;
  return `${formatMinutes(-minutes)} less travel (${label})`;
}

/** What else changes, in plain lines: left out first, then day changes, new bases and new times. */
export function affectedLines(d: ChangeDiff): { tone: "warn" | "info"; text: string }[] {
  const lines: { tone: "warn" | "info"; text: string }[] = [];
  for (const r of d.removed)
    lines.push({ tone: "warn", text: `Leaves out ${r.name} (day ${r.day})` });
  for (const m of d.moved) {
    lines.push({ tone: "info", text: `${m.name} moves from day ${m.from_day} to day ${m.to_day}` });
  }
  for (const b of d.base_changes) {
    lines.push({
      tone: "info",
      text: `Day ${b.day} is based in ${b.new_base_name ?? "another town"}${b.old_base_name ? ` instead of ${b.old_base_name}` : ""}`,
    });
  }
  for (const r of d.retimed) {
    const what = r.meal_type ? `${MEAL_LABEL[r.meal_type]} at ${r.name}` : r.name;
    lines.push({
      tone: "info",
      text: `${what}: ${clock(r.old_start_time)} → ${clock(r.new_start_time)}`,
    });
  }
  return lines;
}

/** One sentence for a screen reader. */
export function placeSuggestionSentence(s: PlaceSuggestion): string {
  const affected = affectedLines(s.diff).map((l) => l.text);
  return [
    `${s.rank === 1 ? "Best" : `Option ${s.rank}`}: ${placeSuggestionTitle(s)}`,
    placeSuggestionWhere(s),
    travelImpact(s.travel_minutes_added, s.estimated),
    affected.length ? affected.join(". ") : "Nothing else changes",
  ].join(". ");
}
