import type { ItinerarySummary } from "@detour/shared";

import { formatMinutes, formatSeconds, pluralise } from "../util/format";

// The short structured summary of how two proposals differ (product brief, flow 2). Everything is
// derived from numbers the backend computed (`stats`, `diversity_score`); the sentences come from
// fixed templates, never from a model (CLAUDE.md, constraint 1).

export const PROFILE_LABEL: Record<ItinerarySummary["profile"], string> = {
  essentials: "Essentials",
  wider: "Wider",
  manual: "Manual",
};

/** The emphasis of each strategy profile (architecture.md, section 5.3). */
export const PROFILE_EMPHASIS: Record<ItinerarySummary["profile"], string> = {
  essentials: "The best-known sights, compact days, the least travel.",
  wider: "More variety and more of the area, with more travel accepted.",
  manual: "A plan you fill in by hand.",
};

export type ComparisonRow = { key: string; label: string; a: string; b: string };

export type Comparison = {
  rows: ComparisonRow[];
  /** One sentence per measured difference, largest first as the backend's numbers allow. */
  differences: string[];
  /** Whole percent of visits the two plans share, or null when unknown. */
  sharedPercent: number | null;
};

const UNKNOWN = "Not available";

function plural(n: number, one: string): string {
  return pluralise(n, one);
}

export function buildComparison(a: ItinerarySummary, b: ItinerarySummary): Comparison {
  const sa = a.stats;
  const sb = b.stats;
  const nameA = PROFILE_LABEL[a.profile];
  const nameB = PROFILE_LABEL[b.profile];

  const transfers = (s: typeof sa) =>
    s ? `${s.routed_transfers} routed, ${s.estimated_transfers} estimated` : UNKNOWN;

  const rows: ComparisonRow[] = [
    {
      key: "visits",
      label: "Visits",
      a: sa ? String(sa.visits) : UNKNOWN,
      b: sb ? String(sb.visits) : UNKNOWN,
    },
    {
      key: "days",
      label: "Days with visits",
      a: sa ? String(sa.days_with_visits) : UNKNOWN,
      b: sb ? String(sb.days_with_visits) : UNKNOWN,
    },
    {
      key: "meals",
      label: "Meals",
      a: sa ? String(sa.meals ?? 0) : UNKNOWN,
      b: sb ? String(sb.meals ?? 0) : UNKNOWN,
    },
    {
      key: "visit-time",
      label: "Time at the sights",
      a: sa ? formatMinutes(sa.visit_minutes) : UNKNOWN,
      b: sb ? formatMinutes(sb.visit_minutes) : UNKNOWN,
    },
    {
      key: "travel",
      label: "Travel time",
      a: sa ? formatSeconds(sa.travel_seconds) : UNKNOWN,
      b: sb ? formatSeconds(sb.travel_seconds) : UNKNOWN,
    },
    { key: "transfers", label: "Transfers", a: transfers(sa), b: transfers(sb) },
  ];

  const differences: string[] = [];
  if (sa && sb) {
    if (sa.visits !== sb.visits) {
      const [more, fewer, diff] =
        sb.visits > sa.visits
          ? [nameB, nameA, sb.visits - sa.visits]
          : [nameA, nameB, sa.visits - sb.visits];
      differences.push(`${more} has ${plural(diff, "visit")} more than ${fewer}.`);
    }
    if (sa.travel_seconds !== sb.travel_seconds) {
      const bMore = sb.travel_seconds > sa.travel_seconds;
      const diff = Math.abs(sb.travel_seconds - sa.travel_seconds);
      differences.push(
        `${bMore ? nameB : nameA} spends ${formatSeconds(diff)} more travelling than ${bMore ? nameA : nameB}.`,
      );
    }
    if (sa.visit_minutes !== sb.visit_minutes) {
      const bMore = sb.visit_minutes > sa.visit_minutes;
      const diff = Math.abs(sb.visit_minutes - sa.visit_minutes);
      differences.push(
        `${bMore ? nameB : nameA} plans ${formatMinutes(diff)} more at the sights than ${bMore ? nameA : nameB}.`,
      );
    }
  }

  // Both variants of a generation carry the same overlap value.
  const overlap = a.diversity_score ?? b.diversity_score ?? null;
  const sharedPercent = overlap === null ? null : Math.round(overlap * 100);
  if (sharedPercent !== null) {
    differences.push(
      sharedPercent === 0
        ? "The two plans have no visit in common."
        : `About ${sharedPercent} % of the visits are in both plans.`,
    );
  }
  return { rows, differences, sharedPercent };
}

/** The headline numbers of one plan, for its card. */
export function planFacts(plan: ItinerarySummary): string[] {
  const s = plan.stats;
  if (!s) return [];
  return [
    plural(s.visits, "visit"),
    `${formatSeconds(s.travel_seconds)} travelling`,
    `${formatMinutes(s.visit_minutes)} at the sights`,
  ];
}

/** A plan's name and one-line character, from fixed templates (never generated text). */
export function planNames(plan: Pick<ItinerarySummary, "profile">, destination: string) {
  switch (plan.profile) {
    case "essentials":
      return {
        title: `Classic ${destination}`,
        tagline: "The essentials",
        badge: "Best-known sights",
      };
    case "wider":
      return {
        title: `${destination} & beyond`,
        tagline: "A wider experience",
        badge: "More variety",
      };
    default:
      return { title: `${destination}, by hand`, tagline: "Your own plan", badge: null };
  }
}
