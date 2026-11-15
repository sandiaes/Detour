import type { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "../../theme";
import { Icon, type IconName } from "./Icon";

// A drop-down: a boxed field that shows the chosen option and opens a short scrolling list under
// it. Choosing an option closes the list again (the caller does that) and the field shows only the
// choice. Used for the day, the attraction of a document and the place found by a search.

export function Dropdown({
  label,
  placeholder,
  value,
  detail,
  icon = "pin",
  open,
  onToggle,
  children,
  testID,
}: {
  label: string;
  placeholder: string;
  /** The chosen option's title; null when none is chosen. */
  value: string | null;
  /** A quiet second line under the chosen title (its kind and town). */
  detail?: string | null;
  icon?: IconName;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
  testID?: string;
}) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}, ${value ?? "none chosen"}`}
        accessibilityHint={open ? "Closes the list" : "Opens a list to choose from"}
        accessibilityState={{ expanded: open }}
        onPress={onToggle}
        hitSlop={{ top: 4, bottom: 4 }}
        style={[styles.field, open && styles.fieldOpen]}
        testID={testID}
      >
        <Icon name={icon} size={18} color={colors.muted} />
        <View style={styles.text}>
          <Text style={[styles.value, !value && styles.placeholder]} numberOfLines={1}>
            {value ?? placeholder}
          </Text>
          {value && detail ? (
            <Text style={styles.detail} numberOfLines={1}>
              {detail}
            </Text>
          ) : null}
        </View>
        <View style={open ? styles.up : styles.down}>
          <Icon name="chevronRight" size={16} color={colors.muted} />
        </View>
      </Pressable>
      {open ? (
        <ScrollView
          style={styles.list}
          nestedScrollEnabled
          keyboardShouldPersistTaps="handled"
          testID={testID ? `${testID}-list` : undefined}
        >
          {children}
        </ScrollView>
      ) : null}
    </View>
  );
}

/** One option of a drop-down list: a title, a quiet detail line and a tick when chosen. */
export function ChoiceRow({
  title,
  meta,
  icon,
  selected,
  onPress,
  testID,
  accessibilityLabel,
}: {
  title: string;
  meta?: string;
  icon?: IconName;
  selected: boolean;
  onPress: () => void;
  testID?: string;
  accessibilityLabel?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? (meta ? `${title}, ${meta}` : title)}
      accessibilityState={{ selected }}
      onPress={onPress}
      hitSlop={{ top: 2, bottom: 2 }}
      style={({ pressed }) => [
        styles.choice,
        selected && styles.choiceSelected,
        pressed && styles.pressed,
      ]}
      testID={testID}
    >
      {icon ? <Icon name={icon} size={16} color={colors.primary} /> : null}
      <View style={styles.text}>
        <Text style={styles.choiceTitle} numberOfLines={1}>
          {title}
        </Text>
        {meta ? (
          <Text style={styles.detail} numberOfLines={1}>
            {meta}
          </Text>
        ) : null}
      </View>
      {selected ? <Icon name="check" size={16} color={colors.primary} /> : null}
    </Pressable>
  );
}

/** The open list of a drop-down on its own, for a field that is a search box (results under it). */
export function DropdownPanel({ children, testID }: { children: ReactNode; testID?: string }) {
  return (
    <ScrollView
      style={styles.list}
      nestedScrollEnabled
      keyboardShouldPersistTaps="handled"
      testID={testID}
    >
      {children}
    </ScrollView>
  );
}

/** A small heading between groups of options ("Sights", "Towns and cities"). */
export function ChoiceGroupTitle({ title }: { title: string }) {
  return (
    <Text accessibilityRole="header" style={styles.group}>
      {title}
    </Text>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  label: { ...type.caption, color: colors.muted },
  field: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.outline,
    backgroundColor: colors.surface,
  },
  fieldOpen: { borderColor: colors.ink },
  text: { flex: 1, gap: 1 },
  value: { ...type.small, fontWeight: "600", color: colors.text },
  placeholder: { fontWeight: "400", color: colors.muted },
  detail: { ...type.caption, color: colors.muted },
  down: { transform: [{ rotate: "90deg" }] },
  up: { transform: [{ rotate: "-90deg" }] },
  list: {
    maxHeight: 264,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  group: {
    ...type.caption,
    fontWeight: "700",
    color: colors.muted,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xxs,
  },
  choice: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 44,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  choiceTitle: { ...type.small, fontWeight: "600", color: colors.text },
  choiceSelected: { backgroundColor: colors.primarySoft },
  pressed: { opacity: 0.85 },
});
