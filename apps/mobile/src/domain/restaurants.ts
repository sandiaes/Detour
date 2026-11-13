import type { SlotSuggestion } from "@detour/shared";

import { formatClock, formatCuisines, formatMinutes } from "../util/format";

// Adding a restaurant (Phase 8, ADR 019): how the entry form and the suggested slots read. The
// slots, reasons and numbers are the server's; nothing here scores or decides anything.

export const MEALS = ["breakfast", "lunch", "snack", "dinner"] as const;
export type Meal = (typeof MEALS)[number];

export const MEAL_LABEL: Record<Meal, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  snack: "Afternoon snack",
  dinner: "Dinner",
};

/** "italian, Pizza ; sushi" → ["italian", "pizza", "sushi"] (the form the open data uses:
 * lower case, spaces as underscores, distinct). Nothing typed means the cuisine is not specified,
 * so undefined, never an empty list. */
export function parseCuisines(text: string): string[] | undefined {
  const values = text
    .split(/[;,]/)
    .map((v) => v.trim().toLowerCase().replace(/\s+/g, "_"))
    .filter((v) => v.length > 0);
  const distinct = [...new Set(values)];
  return distinct.length ? distinct.slice(0, 10) : undefined;
}

/** A typed coordinate ("48.2082", also "48,2082"), or null when it is not a valid one. */
export function parseCoordinate(text: string, axis: "lat" | "lon"): number | null {
  const cleaned = text.trim().replace(",", ".");
  if (!/^[+-]?\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  const limit = axis === "lat" ? 90 : 180;
  return Math.abs(value) <= limit ? value : null;
}

/** "Lunch, dinner", or the plain statement that the meals are not known. */
export function formatMealTypes(meals: string[] | null | undefined): string {
  if (!meals || meals.length === 0) return "Meals not specified";
  return MEALS.filter((m) => meals.includes(m))
    .map((m) => MEAL_LABEL[m])
    .join(", ");
}

/** The one line a search result shows: cuisine (or that it is not specified), venue and meals. */
export function restaurantMeta(r: {
  cuisines?: string[] | null;
  venue_type?: string | null;
  meal_types?: string[] | null;
  city_name?: string | null;
}): string {
  return [
    formatCuisines(r.cuisines),
    r.venue_type === "cafe" ? "Café" : r.venue_type === "restaurant" ? "Restaurant" : null,
    formatMealTypes(r.meal_types),
    r.city_name ?? null,
  ]
    .filter(Boolean)
    .join(" · ");
}

const clock = (t: string) => formatClock(t) ?? t;

/** "Day 2 · Lunch · 12:15–13:15". */
export function suggestionTitle(s: SlotSuggestion): string {
  return `Day ${s.day} · ${MEAL_LABEL[s.meal_type]} · ${clock(s.start_time)}–${clock(s.end_time)}`;
}

/** Where the meal sits between the stops of the day. */
export function suggestionPlace(s: SlotSuggestion): string {
  if (s.after_name && s.before_name) return `Between ${s.after_name} and ${s.before_name}`;
  if (s.after_name) return `After ${s.after_name}, the last stop of the day`;
  if (s.before_name) return `Before ${s.before_name}, the first stop of the day`;
  return "On its own in the day";
}

/** The estimated detour, labelled routed or estimated like every travel time. */
export function detourText(s: SlotSuggestion): string {
  const label = s.travel_label === "estimated" ? "estimated" : "routed";
  if (s.travel_minutes_added === 0) return `No extra travel (${label})`;
  const sign = s.travel_minutes_added > 0 ? "+" : "−";
  return `${sign}${formatMinutes(Math.abs(s.travel_minutes_added))} travel that day (${label})`;
}

/** Which other items move, in the server's words, or that nothing does. */
export function movedLines(s: SlotSuggestion): string[] {
  if (s.items_moved.length === 0) return ["No other item moves."];
  return [
    `${s.items_moved.length === 1 ? "1 other item starts" : `${s.items_moved.length} other items start`} at another time:`,
    ...s.items_moved.map(
      (m) => `${m.name} ${clock(m.old_start_time)} → ${clock(m.new_start_time)}`,
    ),
  ];
}
