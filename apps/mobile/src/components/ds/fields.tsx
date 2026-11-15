import { type ReactNode, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
} from "react-native";

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
import { IconButton, ListRow } from "./primitives";

// Fields (docs/design.md, "Field"). One shell for every input: a small label over a 44 dp box with
// 12 dp corners and a 1 dp outline (3:1 or more), the value in 15 pt, an optional leading icon,
// suffix and clear button, and a hint or an error under it. Text, search, select (a drop-down) and
// date fields are this shell with different insides.

/** The label, the box and the hint or error of a field. */
export function FieldShell({
  label,
  hint,
  error,
  children,
}: {
  label?: string;
  hint?: string | null;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <View style={styles.wrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      {children}
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

export type TextFieldProps = TextInputProps & {
  label?: string;
  /** A line icon before the text (a magnifier on a search field). */
  icon?: IconName;
  suffix?: string;
  error?: string | null;
  hint?: string | null;
  /** A muted fill, for a value that is a default rather than the user's own. */
  quiet?: boolean;
  /** Shows a clear button while there is text. */
  onClear?: () => void;
  clearLabel?: string;
};

/** A text input in the field shell. Multiline grows from three lines. */
export function TextField({
  label,
  icon,
  suffix,
  error,
  hint,
  quiet = false,
  onClear,
  clearLabel = "Clear",
  multiline,
  ...input
}: TextFieldProps) {
  const [focused, setFocused] = useState(false);
  const hasText = typeof input.value === "string" && input.value.length > 0;
  return (
    <FieldShell label={label} hint={hint} error={error}>
      <View
        style={[
          styles.box,
          multiline && styles.boxMultiline,
          quiet && styles.boxQuiet,
          focused && styles.boxFocused,
          error ? styles.boxError : null,
        ]}
      >
        {icon ? <Icon name={icon} size="sm" color={colors.muted} /> : null}
        <TextInput
          {...input}
          multiline={multiline}
          accessibilityLabel={input.accessibilityLabel ?? label}
          accessibilityHint={input.accessibilityHint ?? hint ?? undefined}
          placeholderTextColor={colors.muted}
          onFocus={(e) => {
            setFocused(true);
            input.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            input.onBlur?.(e);
          }}
          style={[
            styles.input,
            multiline && styles.inputMultiline,
            quiet && styles.inputQuiet,
            input.style,
          ]}
        />
        {suffix ? <Text style={styles.suffix}>{suffix}</Text> : null}
        {onClear && hasText ? (
          <IconButton icon="close" label={clearLabel} size="sm" onPress={onClear} />
        ) : null}
      </View>
    </FieldShell>
  );
}

/** A search field: a text field with a magnifier and a clear button. */
export function SearchField(props: Omit<TextFieldProps, "icon">) {
  return (
    <TextField
      icon="search"
      returnKeyType="search"
      autoCorrect={false}
      clearLabel="Clear the search"
      {...props}
    />
  );
}

/**
 * A field that is pressed rather than typed in: a drop-down (`open` and children: the list opens
 * under it) or a date (it opens a calendar). It shows the chosen value with an optional quiet second
 * line, or the placeholder.
 */
export function SelectField({
  label,
  placeholder,
  value,
  detail,
  icon = "pin",
  open,
  onToggle,
  onPress,
  onClear,
  clearLabel,
  hint,
  error,
  accessibilityLabel,
  accessibilityHint,
  children,
  testID,
}: {
  label?: string;
  placeholder: string;
  /** The chosen value; null when none is chosen. */
  value: string | null;
  /** A quiet second line under the value (its kind and town). */
  detail?: string | null;
  icon?: IconName;
  /** A drop-down: whether its list is open. Leave out for a field that opens something else. */
  open?: boolean;
  onToggle?: () => void;
  /** For a field that opens something else (a calendar). */
  onPress?: () => void;
  /** Shows a clear button while a value is chosen. */
  onClear?: () => void;
  clearLabel?: string;
  hint?: string | null;
  error?: string | null;
  accessibilityLabel?: string;
  accessibilityHint?: string;
  children?: ReactNode;
  testID?: string;
}) {
  const dropdown = open !== undefined;
  const spokenName = label ?? placeholder;
  return (
    <FieldShell label={label} hint={hint} error={error}>
      <View style={[styles.box, open && styles.boxFocused, error ? styles.boxError : null]}>
        {dropdown || onPress ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={accessibilityLabel ?? `${spokenName}, ${value ?? "none chosen"}`}
            accessibilityHint={
              accessibilityHint ??
              (dropdown ? (open ? "Closes the list" : "Opens a list to choose from") : undefined)
            }
            accessibilityState={dropdown ? { expanded: open } : undefined}
            onPress={dropdown ? onToggle : onPress}
            hitSlop={touchSlop(sizes.control - 2 * border.thin)}
            style={({ pressed }) => [styles.select, pressed && styles.pressed]}
            testID={testID}
          >
            <Icon name={icon} size="sm" color={colors.muted} />
            <View style={styles.selectText}>
              <Text style={[styles.value, !value && styles.placeholder]} numberOfLines={1}>
                {value ?? placeholder}
              </Text>
              {value && detail ? (
                <Text style={styles.detail} numberOfLines={1}>
                  {detail}
                </Text>
              ) : null}
            </View>
            {dropdown ? <Icon name={open ? "up" : "down"} size="sm" color={colors.muted} /> : null}
          </Pressable>
        ) : (
          // A chosen value shown read-only (a destination, cleared with the button beside it).
          <View
            style={styles.select}
            accessible
            accessibilityLabel={accessibilityLabel ?? `${spokenName}, ${value ?? "none chosen"}`}
            testID={testID}
          >
            <Icon name={icon} size="sm" color={colors.muted} />
            <View style={styles.selectText}>
              <Text style={[styles.value, !value && styles.placeholder]} numberOfLines={1}>
                {value ?? placeholder}
              </Text>
              {value && detail ? (
                <Text style={styles.detail} numberOfLines={1}>
                  {detail}
                </Text>
              ) : null}
            </View>
            {dropdown ? <Icon name={open ? "up" : "down"} size="sm" color={colors.muted} /> : null}
          </View>
        )}
        {onClear && value ? (
          <IconButton icon="close" label={clearLabel ?? "Clear"} size="sm" onPress={onClear} />
        ) : null}
      </View>
      {dropdown && open ? (
        <DropdownPanel testID={testID ? `${testID}-list` : undefined}>{children}</DropdownPanel>
      ) : null}
    </FieldShell>
  );
}

/** The open list of a drop-down on its own, for a search field with its results under it. */
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

/** One option of a drop-down: a compact list row with a tick when chosen. */
export function ChoiceRow({
  title,
  meta,
  icon,
  selected,
  onPress,
  disabled,
  disabledLabel,
  testID,
  accessibilityLabel,
}: {
  title: string;
  meta?: string;
  icon?: IconName;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
  disabledLabel?: string;
  testID?: string;
  accessibilityLabel?: string;
}) {
  return (
    <ListRow
      icon={icon}
      title={title}
      detail={meta}
      density="compact"
      inset="panel"
      selected={selected}
      disabled={disabled}
      disabledLabel={disabledLabel}
      trailing={selected ? <Icon name="check" size="sm" color={colors.selected} /> : null}
      accessibilityLabel={accessibilityLabel ?? (meta ? `${title}, ${meta}` : title)}
      onPress={onPress}
      testID={testID}
    />
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

/** A number chosen with minus and plus (days of a trip, days in a city). The value is adjustable
 * with a screen reader's swipe too. */
export function Stepper({
  value,
  min,
  max,
  onChange,
  format,
  accessibilityLabel,
  decreaseLabel,
  increaseLabel,
  testID,
}: {
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  format: (value: number) => string;
  /** The spoken name of the value ("Days"). */
  accessibilityLabel: string;
  decreaseLabel: string;
  increaseLabel: string;
  /** Prefix of the buttons' test IDs (`-fewer`, `-more`). */
  testID?: string;
}) {
  const text = format(value);
  const step = (by: number, label: string, icon: IconName, off: boolean, id: string) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: off }}
      disabled={off}
      onPress={() => onChange(value + by)}
      hitSlop={touchSlop(sizes.controlSm, spacing.xs)}
      style={({ pressed }) => [styles.step, pressed && styles.pressed, off && styles.stepOff]}
      testID={testID ? `${testID}-${id}` : undefined}
    >
      <Icon name={icon} size="sm" color={colors.text} />
    </Pressable>
  );
  return (
    <View style={styles.stepper}>
      {step(-1, decreaseLabel, "minus", value <= min, "fewer")}
      <View
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel={accessibilityLabel}
        accessibilityValue={{ min, max, now: value, text }}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(e) => {
          if (e.nativeEvent.actionName === "increment" && value < max) onChange(value + 1);
          if (e.nativeEvent.actionName === "decrement" && value > min) onChange(value - 1);
        }}
        style={styles.stepValue}
      >
        <Text style={styles.stepText}>{text}</Text>
      </View>
      {step(1, increaseLabel, "add", value >= max, "more")}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  label: { ...type.caption, color: colors.muted, fontWeight: weight.medium },
  hint: { ...type.caption, color: colors.muted },
  error: { ...type.caption, color: colors.danger, fontWeight: weight.semibold },
  box: {
    minHeight: sizes.control,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingLeft: spacing.md,
    paddingRight: spacing.xs,
    borderWidth: border.thin,
    borderColor: colors.outline,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  boxMultiline: { alignItems: "flex-start", paddingVertical: spacing.xs },
  boxQuiet: { backgroundColor: colors.surfaceMuted },
  boxFocused: { borderColor: colors.selected },
  boxError: { borderColor: colors.danger },
  input: {
    flex: 1,
    ...type.body,
    color: colors.text,
    minHeight: sizes.control - 2 * border.thin,
    paddingVertical: spacing.xs,
    paddingRight: spacing.sm,
  },
  inputMultiline: { minHeight: 72, textAlignVertical: "top" },
  inputQuiet: { color: colors.muted },
  suffix: { ...type.caption, color: colors.muted, marginRight: spacing.sm },
  select: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: sizes.control - 2 * border.thin,
    paddingVertical: spacing.xs,
    paddingRight: spacing.sm,
  },
  selectText: { flex: 1, gap: 1 },
  value: { ...type.body, color: colors.text },
  placeholder: { color: colors.muted },
  detail: { ...type.caption, color: colors.muted },
  pressed: { opacity: opacity.pressed },
  list: {
    maxHeight: 264,
    borderRadius: radius.md,
    borderWidth: border.hairline,
    borderColor: colors.outline,
    backgroundColor: colors.surface,
  },
  group: {
    ...type.caption,
    fontWeight: weight.bold,
    color: colors.muted,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xxs,
  },
  stepper: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  step: {
    width: sizes.controlSm,
    height: sizes.controlSm,
    minHeight: sizes.controlSm,
    borderRadius: radius.pill,
    borderWidth: border.thin,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  stepOff: { opacity: opacity.disabled },
  stepValue: { minWidth: 56, alignItems: "center", justifyContent: "center" },
  stepText: { ...type.label, fontWeight: weight.semibold, color: colors.text },
});
