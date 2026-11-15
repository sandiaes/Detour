import { Pressable, StyleSheet, Text, View } from "react-native";

import { border, colors, size as sizes, spacing, type, weight } from "../../theme";
import { Badge, Bullets, MetaLine, Radio } from "./primitives";

export type AffectedLine = { tone: "warn" | "info"; text: string };

/**
 * One suggested placement (a day and time for a place): where it goes, the travel it adds, what
 * else changes, and why. A selectable row with the shared radio mark; the first is marked "Best" in
 * words; the chosen one is tinted and announced.
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
      style={({ pressed }) => [styles.row, (selected || pressed) && styles.selected]}
    >
      <View style={styles.head}>
        <Radio on={selected} />
        <Text style={styles.title}>{title}</Text>
        {rank === 1 ? <Badge label="Best" tone="primary" /> : null}
      </View>
      <View style={styles.body}>
        <MetaLine icon="pin" text={where} tone="text" />
        <MetaLine icon="route" text={impact} tone="text" />
        {affected.length === 0 ? (
          <MetaLine icon="check" text="Nothing else changes" tone="text" />
        ) : (
          <View style={styles.group}>
            <Text style={styles.label}>Also changes</Text>
            {affected.map((a) => (
              <MetaLine
                key={a.text}
                icon={a.tone === "warn" ? "alert" : "clock"}
                text={a.text}
                tone={a.tone === "warn" ? "danger" : "muted"}
              />
            ))}
          </View>
        )}
        {reasons.length > 0 ? (
          <View style={styles.group}>
            <Text style={styles.label}>Why here</Text>
            <Bullets items={reasons} tone="muted" />
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: sizes.row,
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  selected: { backgroundColor: colors.selectedSoft },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  // The lines start under the title, past the radio mark.
  body: { gap: spacing.xs, paddingLeft: 20 + spacing.md },
  title: { ...type.cardTitle, color: colors.text, flex: 1 },
  group: { gap: spacing.xs, marginTop: spacing.xs },
  label: { ...type.caption, fontWeight: weight.bold, color: colors.muted },
});
