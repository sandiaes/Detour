// Adding a restaurant or café (ADR 019, narrowed by ADR 026): the form reads only what Photon can
// give: a name, a point and the kind. The user chooses the day and time.

export const VENUES = ["restaurant", "cafe"] as const;
export type Venue = (typeof VENUES)[number];

export const VENUE_LABEL: Record<Venue, string> = { restaurant: "Restaurant", cafe: "Café" };

/** "Restaurant" or "Café"; the plain statement that the kind is not known for anything else. */
export function venueLabel(kind: string | null | undefined): string {
  return kind === "restaurant" || kind === "cafe" ? VENUE_LABEL[kind] : "Restaurant or café";
}

/** A typed coordinate ("48.2082", also "48,2082"), or null when it is not a valid one. */
export function parseCoordinate(text: string, axis: "lat" | "lon"): number | null {
  const cleaned = text.trim().replace(",", ".");
  if (!/^[+-]?\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  const limit = axis === "lat" ? 90 : 180;
  return Math.abs(value) <= limit ? value : null;
}

/** The length offered first for a restaurant or café the user adds (ADR 026, proposed; the same
 * numbers as the server's, which it uses when "default" is chosen). */
export const VENUE_DEFAULT_MINUTES: Record<Venue, number> = { restaurant: 75, cafe: 45 };
