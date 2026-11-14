import { Pressable, StyleSheet, Text, View } from "react-native";

import { TOUCH, colors, spacing, type } from "../../theme";
import { Icon } from "./Icon";
import { Badge } from "./primitives";

export type AffectedLine = { tone: "warn" | "info"; text: string };

/**
 * One suggested placement (a day and time for a place, or a day and meal for a restaurant):
 * where it goes, the travel it adds, what else changes, and why. The first is marked "Best" in
 * words; the chosen one has a thick border, a check and the announced state.
 */
export function SuggestionCard({
  rank,
  title,
  where,
  impact,
  affected,
  reasons,
  selected,
  onPress,
  accessibilityLabel,
  testID,
}: {
  rank: number;
  title: string;
  where: string;
  impact: string;
  affected: AffectedLine[];
  reasons: string[];
  selected: boolean;
  onPress: () => void;
  accessibilityLabel: string;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ selected }}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [styles.card, selected && styles.selected, pressed && styles.pressed]}
    >
      <View style={styles.head}>
        <View style={[styles.radio, selected && styles.radioOn]}>
          {selected ? (
            <Icon name="check" size={16} color={colors.onPrimary} strokeWidth={2.4} />
          ) : null}
        </View>
        <Text style={styles.title}>{title}</Text>
        {rank === 1 ? <Badge label="Best" tone="primary" /> : null}
      </View>
      <View style={styles.line}>
        <Icon name="pin" size={16} color={colors.muted} />
        <Text style={styles.text}>{where}</Text>
      </View>
      <View style={styles.line}>
        <Icon name="route" size={16} color={colors.muted} />
        <Text style={styles.text}>{impact}</Text>
      </View>
      {affected.length === 0 ? (
        <View style={styles.line}>
          <Icon name="check" size={16} color={colors.primary} />
          <Text style={styles.text}>Nothing else changes</Text>
        </View>
      ) : (
        <View style={styles.affected}>
          <Text style={styles.label}>Also changes</Text>
          {affected.map((a) => (
            <View key={a.text} style={styles.line}>
              <Icon
                name={a.tone === "warn" ? "close" : "clock"}
                size={16}
                color={a.tone === "warn" ? colors.errorText : colors.muted}
              />
              <Text style={[styles.text, a.tone === "warn" && styles.warn]}>{a.text}</Text>
            </View>
          ))}
        </View>
      )}
      {reasons.length > 0 ? (
        <View style={styles.reasons}>
          <Text style={styles.label}>Why here</Text>
          {reasons.map((r) => (
            <Text key={r} style={styles.reason}>
              • {r}
            </Text>
          ))}
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    minHeight: TOUCH,
    gap: spacing.xs,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  selected: { backgroundColor: colors.surfaceMuted },
  pressed: { opacity: 0.85 },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.xs },
  radio: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  radioOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  title: { ...type.heading, color: colors.text, flex: 1 },
  line: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  text: { ...type.small, color: colors.text, flex: 1 },
  warn: { color: colors.errorText, fontWeight: "600" },
  affected: { gap: spacing.xs, marginTop: spacing.xs },
  label: { ...type.caption, fontWeight: "700", color: colors.muted },
  reasons: { gap: spacing.xxs, marginTop: spacing.xs },
  reason: { ...type.small, color: colors.muted },
});
