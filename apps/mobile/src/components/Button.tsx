import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";

import { TOUCH, colors, radius, spacing, type } from "../theme";
import { Icon, type IconName } from "./ds/Icon";

type Props = {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "quiet" | "accent" | "ink";
  /** A line icon before the label. */
  icon?: IconName;
  disabled?: boolean;
  loading?: boolean;
  /** Read after the label by a screen reader, for example what the button will do. */
  hint?: string;
  /** Overrides the spoken label when the visible one is not enough ("Select" -> "Select Wider"). */
  accessibilityLabel?: string;
  fill?: boolean;
  /** "compact": a slimmer pill with smaller text (36 dp, plus hit slop for a 48 dp touch). */
  size?: "regular" | "compact";
  testID?: string;
};

export function Button({
  label,
  onPress,
  variant = "primary",
  disabled = false,
  loading = false,
  hint,
  accessibilityLabel,
  fill = false,
  size = "regular",
  testID,
  icon,
}: Props) {
  const compact = size === "compact";
  const inactive = disabled || loading;
  const filled = variant === "primary" || variant === "accent" || variant === "ink";
  const labelColor = filled ? colors.onPrimary : variant === "quiet" ? colors.primary : colors.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={hint}
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      testID={testID}
      hitSlop={compact ? { top: 6, bottom: 6 } : undefined}
      style={({ pressed }) => [
        styles.base,
        compact && styles.compact,
        compact && variant === "secondary" && styles.compactSecondary,
        variant === "primary" && styles.primary,
        variant === "secondary" && styles.secondary,
        variant === "quiet" && styles.quiet,
        variant === "accent" && styles.accent,
        variant === "ink" && styles.ink,
        fill && styles.fill,
        inactive && styles.inactive,
        pressed && styles.pressed,
      ]}
    >
      {loading ? <ActivityIndicator color={labelColor} /> : null}
      {icon && !loading ? <Icon name={icon} size={compact ? 16 : 20} color={labelColor} /> : null}
      <Text
        style={[
          styles.label,
          filled
            ? styles.labelOnPrimary
            : variant === "quiet"
              ? styles.labelQuiet
              : styles.labelOnLight,
          compact && styles.labelCompact,
          // Disabled is shown by a lighter fill AND by the state read aloud, never colour alone:
          // the label stays at full contrast.
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: TOUCH,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    alignSelf: "flex-start",
  },
  fill: { alignSelf: "stretch" },
  compact: { minHeight: 36, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, gap: 6 },
  compactSecondary: { borderWidth: 1, borderColor: colors.outline },
  labelCompact: { ...type.small, fontSize: 13, lineHeight: 18 },
  primary: { backgroundColor: colors.primary },
  accent: { backgroundColor: colors.accent },
  ink: { backgroundColor: colors.ink },
  // Outlined: a thin grey-blue line and dark text, the same look at every size.
  secondary: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.outline },
  quiet: { backgroundColor: "transparent" },
  inactive: { opacity: 0.55 },
  pressed: { opacity: 0.8 },
  label: { ...type.body, fontWeight: "600", flexShrink: 1, textAlign: "center" },
  labelOnPrimary: { color: colors.onPrimary },
  labelOnLight: { color: colors.text },
  labelQuiet: { color: colors.primary },
});
