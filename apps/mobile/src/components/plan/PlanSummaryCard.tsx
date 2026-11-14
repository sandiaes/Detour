import type { ItinerarySummary, Photo } from "@detour/shared";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { planNames } from "../../domain/compare";
import { card, colors, radius, spacing, type } from "../../theme";
import { formatSeconds, pluralise } from "../../util/format";
import { Cover } from "../ds/Cover";
import { Icon } from "../ds/Icon";
import { Badge, type BadgeTone } from "../ds/primitives";

/** "8 places · 6 restaurants · 2 h travelling", from the plan's own numbers; empty without any. */
export function planLine(plan: Pick<ItinerarySummary, "stats">): string {
  const s = plan.stats;
  if (!s) return "";
  return [
    pluralise(s.visits, "place"),
    (s.meals ?? 0) > 0 ? pluralise(s.meals ?? 0, "restaurant") : null,
    `${formatSeconds(s.travel_seconds)} travelling`,
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * A plan as a compact card (reference screen 02, "Your itineraries"): a small cover, the plan's
 * name, what it is, its numbers, a badge and a chevron. Pressing it opens the plan.
 */
export function PlanSummaryCard({
  plan,
  destination,
  coverKey,
  photo,
  badge,
  badgeTone = "primary",
  hint,
  onPress,
  testID,
}: {
  plan: Pick<ItinerarySummary, "profile" | "stats">;
  destination: string;
  coverKey: string;
  photo?: Photo | null;
  /** Only the active plan carries a badge; another plan has none. */
  badge?: string;
  badgeTone?: BadgeTone;
  hint: string;
  onPress: () => void;
  testID?: string;
}) {
  const names = planNames(plan, destination);
  const line = planLine(plan);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${names.title}. ${names.tagline}. ${line ? `${line}. ` : ""}${badge ? `${badge}.` : ""}`}
      accessibilityHint={hint}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <Cover
        seedKey={`${coverKey}:${plan.profile}`}
        photo={photo}
        height={56}
        rounded={radius.md}
        style={styles.thumb}
      />
      <View style={styles.text}>
        <View style={styles.head}>
          <Text style={styles.title} numberOfLines={1}>
            {names.title}
          </Text>
          {badge ? <Badge label={badge} tone={badgeTone} /> : null}
        </View>
        <Text style={styles.tagline} numberOfLines={1}>
          {names.tagline}
        </Text>
        {line ? (
          <Text style={styles.line} numberOfLines={1}>
            {line}
          </Text>
        ) : null}
      </View>
      <Icon name="chevronRight" size={16} color={colors.muted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: 48,
    padding: spacing.sm,
  },
  pressed: { opacity: 0.85 },
  thumb: { width: 56 },
  text: { flex: 1, gap: 2 },
  head: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  title: { ...type.small, fontWeight: "700", color: colors.text, flexShrink: 1 },
  tagline: { ...type.caption, color: colors.muted },
  line: { ...type.caption, color: colors.muted },
});
