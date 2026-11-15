import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, layout, spacing, touchSlop, type, weight } from "../../theme";
import { Bullets } from "../ds/primitives";
import { Icon } from "../ds/Icon";

/**
 * Plan-level explanations from the backend (opening hours not checked, durations are defaults, ...).
 * Collapsed by default because there are several, but never hidden: product brief, section 7.
 */
export function PlanNotes({
  notes,
  defaultOpen = false,
  inset = true,
}: {
  notes: { code: string; text: string }[];
  /** Shown open: for a note the user must read before accepting (Optimize, ADR 029). */
  defaultOpen?: boolean;
  /** With the screen gutter (a parent without padding). */
  inset?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (notes.length === 0) return null;
  return (
    <View style={[styles.notes, inset && styles.inset]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`About these plans, ${notes.length} notes`}
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((o) => !o)}
        hitSlop={touchSlop(40)}
        style={styles.toggle}
      >
        <Icon name={open ? "down" : "chevronRight"} size="sm" color={colors.primary} />
        <Text style={styles.toggleText}>About these plans ({notes.length})</Text>
      </Pressable>
      {open ? <Bullets items={notes.map((n) => n.text)} tone="muted" /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  notes: { gap: spacing.xs, marginBottom: spacing.sm },
  inset: { marginHorizontal: layout.gutter },
  toggle: { minHeight: 40, flexDirection: "row", alignItems: "center", gap: spacing.xs },
  toggleText: { ...type.label, color: colors.primary, fontWeight: weight.semibold },
});
