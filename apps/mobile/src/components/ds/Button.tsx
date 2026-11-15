import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";

import {
  border,
  colors,
  opacity,
  radius,
  size as sizes,
  spacing,
  touchSlop,
  type,
  weight,
} from "../../theme";
import { Icon, type IconName } from "./Icon";

// The one button (docs/design.md, "Button"). Four variants with fixed roles:
// - primary: the screen's main action (filled deep green). At most one per screen or sheet.
// - secondary: a second action, or an action among equals (outlined).
// - ghost: a third, quiet action (text only).
// - destructive: the button that confirms a deletion or an action that cannot be undone (filled red).
// `tone="danger"` marks a secondary or ghost button that leads to a destructive confirmation
// ("Delete trip"). Two sizes: md (44 dp) for a screen's actions, sm (36 dp) for actions inside a
// card, a row or a form. Both reach a 48 dp touch with hit slop. States: pressed, disabled, loading
// and focused (a 2 dp ring), each also announced.

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
export type ButtonSize = "md" | "sm";

type Props = {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  tone?: "default" | "danger";
  size?: ButtonSize;
  /** A line icon before the label. */
  icon?: IconName;
  disabled?: boolean;
  loading?: boolean;
  /** Read after the label by a screen reader, for example what the button will do. */
  hint?: string;
  /** Overrides the spoken label when the visible one is not enough ("Select" -> "Select Wider"). */
  accessibilityLabel?: string;
  /** Stretch to the width of the parent. */
  fill?: boolean;
  testID?: string;
};

function labelColour(variant: ButtonVariant, danger: boolean): string {
  if (variant === "primary") return colors.onPrimary;
  if (variant === "destructive") return colors.onDanger;
  if (danger) return colors.danger;
  return variant === "ghost" ? colors.primary : colors.text;
}

export function Button({
  label,
  onPress,
  variant = "primary",
  tone = "default",
  size = "md",
  icon,
  disabled = false,
  loading = false,
  hint,
  accessibilityLabel,
  fill = false,
  testID,
}: Props) {
  const [focused, setFocused] = useState(false);
  const inactive = disabled || loading;
  const danger = tone === "danger";
  const colour = labelColour(variant, danger);
  const height = size === "sm" ? sizes.controlSm : sizes.control;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={hint}
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      testID={testID}
      hitSlop={touchSlop(height)}
      style={({ pressed }) => [
        styles.base,
        { minHeight: height },
        size === "sm" ? styles.sm : styles.md,
        variant === "primary" && styles.primary,
        variant === "primary" && pressed && styles.primaryPressed,
        variant === "secondary" && styles.secondary,
        variant === "secondary" && danger && styles.secondaryDanger,
        variant === "destructive" && styles.destructive,
        (variant === "secondary" || variant === "ghost") && pressed && styles.quietPressed,
        variant === "destructive" && pressed && styles.pressed,
        fill && styles.fill,
        inactive && styles.inactive,
        focused && styles.focused,
      ]}
    >
      {loading ? <ActivityIndicator size="small" color={colour} /> : null}
      {icon && !loading ? (
        <Icon name={icon} size={size === "sm" ? "sm" : "md"} color={colour} />
      ) : null}
      <Text
        style={[styles.label, size === "sm" ? styles.labelSm : styles.labelMd, { color: colour }]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    alignSelf: "flex-start",
    borderWidth: border.thin,
    borderColor: "transparent",
  },
  md: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  sm: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, gap: spacing.xs },
  fill: { alignSelf: "stretch" },
  primary: { backgroundColor: colors.primary, borderColor: colors.primary },
  primaryPressed: { backgroundColor: colors.primaryPressed, borderColor: colors.primaryPressed },
  secondary: { backgroundColor: colors.surface, borderColor: colors.outline },
  secondaryDanger: { borderColor: colors.danger },
  destructive: { backgroundColor: colors.danger, borderColor: colors.danger },
  quietPressed: { backgroundColor: colors.surfaceMuted },
  pressed: { opacity: opacity.pressed },
  inactive: { opacity: opacity.disabled },
  focused: { borderColor: colors.selected, borderWidth: border.thick },
  label: { fontWeight: weight.semibold, flexShrink: 1, textAlign: "center" },
  labelMd: { ...type.body },
  labelSm: { ...type.label },
});
