import { StyleSheet, Text, TextInput, type TextInputProps, View } from "react-native";

import { colors, radius, spacing, type } from "../../theme";
import { Icon, type IconName } from "./Icon";

// A slim boxed input: a small label over a 40 dp box with an optional suffix ("min"). The shape of
// the add-a-place screens' fields and of the length field (owner request, 2026-11-15).

export function BoxField({
  label,
  suffix,
  icon,
  error,
  hint,
  quiet = false,
  ...input
}: TextInputProps & {
  label: string;
  /** A line icon before the text (a magnifier on a search field). */
  icon?: IconName;
  suffix?: string;
  error?: string | null;
  hint?: string;
  /** A muted fill, for a value that is a default rather than the user's own. */
  quiet?: boolean;
}) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={[styles.box, quiet && styles.boxQuiet, error ? styles.boxError : null]}>
        {icon ? <Icon name={icon} size={16} color={colors.muted} /> : null}
        <TextInput
          {...input}
          accessibilityLabel={input.accessibilityLabel ?? label}
          accessibilityHint={hint}
          placeholderTextColor={colors.muted}
          hitSlop={{ top: 4, bottom: 4 }}
          style={[styles.input, quiet && styles.inputQuiet]}
        />
        {suffix ? <Text style={styles.suffix}>{suffix}</Text> : null}
      </View>
      {error ? (
        <Text style={styles.error} accessibilityLiveRegion="polite">
          Problem: {error}
        </Text>
      ) : hint ? (
        <Text style={styles.hint}>{hint}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  label: { ...type.caption, color: colors.muted },
  box: {
    height: 40,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.outline,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
  },
  boxQuiet: { backgroundColor: colors.surfaceMuted },
  boxError: { borderColor: colors.errorText },
  input: { flex: 1, ...type.small, color: colors.text, paddingVertical: 0, marginLeft: 0 },
  inputQuiet: { color: colors.muted },
  suffix: { ...type.caption, color: colors.muted, marginLeft: spacing.sm },
  hint: { ...type.caption, color: colors.muted },
  error: { ...type.caption, color: colors.errorText, fontWeight: "600" },
});
