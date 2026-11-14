import { formatCuisines } from "../util/format";

// Adding a restaurant (Phase 8, ADR 019): how the entry form reads. The suggested slots of Phase 8
// were retired by ADR 026: the user chooses the day and time.

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
