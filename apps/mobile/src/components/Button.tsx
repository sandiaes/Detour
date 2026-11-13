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
  testID,
  icon,
}: Props) {
  const inactive = disabled || loading;
  const filled = variant === "primary" || variant === "accent" || variant === "ink";
  const labelColor = filled ? colors.onPrimary : colors.primary;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={hint}
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.base,
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
      {icon && !loading ? <Icon name={icon} size={20} color={labelColor} /> : null}
      <Text
        style={[
          styles.label,
          filled ? styles.labelOnPrimary : styles.labelOnLight,
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
  primary: { backgroundColor: colors.primary },
  accent: { backgroundColor: colors.accent },
  ink: { backgroundColor: colors.ink },
  secondary: { backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.primary },
  quiet: { backgroundColor: "transparent" },
  inactive: { opacity: 0.55 },
  pressed: { opacity: 0.8 },
  label: { ...type.body, fontWeight: "600", flexShrink: 1, textAlign: "center" },
  labelOnPrimary: { color: colors.onPrimary },
  labelOnLight: { color: colors.primary },
});
