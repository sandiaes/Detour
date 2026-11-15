import { type ComponentRef, type ReactNode, useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
  findNodeHandle,
} from "react-native";

import { TOUCH, colors, radius, spacing, type } from "../theme";
import { Button } from "./Button";
import { Icon, type IconName } from "./ds/Icon";
import { IconButton } from "./ds/primitives";

// ---- header ------------------------------------------------------------------------------------

/** Moves the screen reader to the element when the screen appears (a screen change). */
export function useAnnounceOnMount() {
  const ref = useRef<ComponentRef<typeof View>>(null);
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        const node = ref.current ? findNodeHandle(ref.current) : null;
        if (node) AccessibilityInfo.setAccessibilityFocus(node);
      } catch {
        // Focus is a nicety; a failure must never break a screen.
      }
    }, 200);
    return () => clearTimeout(id);
  }, []);
  return ref;
}

export function ScreenHeader({
  title,
  subtitle,
  onBack,
  right,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: ReactNode;
}) {
  const ref = useAnnounceOnMount();
  return (
    <View style={styles.header}>
      <View style={styles.headerTop}>
        {onBack ? (
          <View style={styles.back}>
            <IconButton icon="back" label="Back" compact onPress={onBack} />
          </View>
        ) : (
          <View />
        )}
        {right}
      </View>
      <View ref={ref} accessible accessibilityRole="header" accessibilityLabel={title}>
        <Text style={styles.headerTitle}>{title}</Text>
      </View>
      {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

/**
 * The slim header of a screen inside a trip (docs/design.md): Back, the title on one line and an
 * optional icon button on the right. Replaces the large title with round text buttons.
 */
export function CompactHeader({
  title,
  subtitle,
  onBack,
  right,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: ReactNode;
}) {
  const ref = useAnnounceOnMount();
  return (
    <View style={styles.compactHeader}>
      {onBack ? <IconButton icon="back" label="Back" compact onPress={onBack} /> : <View />}
      <View
        ref={ref}
        style={styles.compactText}
        accessible
        accessibilityRole="header"
        accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      >
        <Text style={styles.compactTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.compactSubtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right ?? <View />}
    </View>
  );
}

// ---- notices and states -------------------------------------------------------------------------

type Tone = "info" | "warning" | "error";

/** Tone is carried by the label word as well as the colour. */
const TONE_LABEL: Record<Tone, string> = { info: "Note", warning: "Offline", error: "Problem" };

export function Notice({
  tone,
  label,
  children,
  action,
}: {
  tone: Tone;
  label?: string;
  children: ReactNode;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View
      style={[
        styles.notice,
        tone === "warning" && styles.noticeWarning,
        tone === "error" && styles.noticeError,
        tone === "info" && styles.noticeInfo,
      ]}
      accessibilityLiveRegion="polite"
    >
      <Text style={styles.noticeText}>
        <Text style={styles.noticeLabel}>{label ?? TONE_LABEL[tone]}. </Text>
        {children}
      </Text>
      {action ? <Button label={action.label} variant="secondary" onPress={action.onPress} /> : null}
    </View>
  );
}

export function LoadingState({ text }: { text: string }) {
  return (
    <View
      style={styles.centre}
      accessibilityLiveRegion="polite"
      accessible
      accessibilityLabel={text}
    >
      <ActivityIndicator size="large" color={colors.primary} />
      <Text style={styles.stateText}>{text}</Text>
    </View>
  );
}

/** The cold start of the free host (ADR 005): a calm explanation and a running count. */
export function WakingServer() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <View style={styles.centre}>
      <ActivityIndicator size="large" color={colors.primary} />
      <View accessibilityLiveRegion="polite" accessible>
        <Text style={styles.stateTitle}>Waking the server</Text>
        <Text style={styles.stateText}>
          The free host sleeps when it has been idle. The first request can take about a minute.
          Nothing is wrong, and your saved trips stay available below once they load.
        </Text>
      </View>
      {/* Outside the live region, so a screen reader is not interrupted every second. */}
      <Text style={styles.stateMeta}>Waiting {seconds} s</Text>
    </View>
  );
}

export function EmptyState({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View style={styles.centre}>
      <Text style={styles.stateTitle}>{title}</Text>
      <Text style={styles.stateText}>{text}</Text>
      {action ? <Button label={action.label} onPress={action.onPress} /> : null}
    </View>
  );
}

export function ErrorState({
  title = "Something went wrong",
  text,
  onRetry,
}: {
  title?: string;
  text: string;
  onRetry?: () => void;
}) {
  return (
    <View style={styles.centre} accessibilityLiveRegion="polite">
      <Text style={styles.stateTitle}>{title}</Text>
      <Text style={styles.stateText}>{text}</Text>
      {onRetry ? <Button label="Try again" onPress={onRetry} /> : null}
    </View>
  );
}

// ---- controls ------------------------------------------------------------------------------------

/** A selectable pill. Selected is shown by a check mark and a filled background, and announced. */
export function Chip({
  label,
  selected,
  onPress,
  accessibilityLabel,
  icon,
  testID,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  accessibilityLabel?: string;
  /** A line icon before the label; it then stands in for the check mark. */
  icon?: IconName;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ selected }}
      onPress={onPress}
      testID={testID}
      hitSlop={{ top: 6, bottom: 6 }}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      {icon ? (
        <Icon
          name={selected ? "check" : icon}
          size={16}
          color={selected ? colors.primary : colors.text}
        />
      ) : null}
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>
        {!icon && selected ? "✓ " : ""}
        {label}
      </Text>
    </Pressable>
  );
}

export function Field({
  label,
  hint,
  error,
  ...input
}: TextInputProps & { label: string; hint?: string; error?: string | null }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        {...input}
        accessibilityLabel={label}
        accessibilityHint={hint}
        placeholderTextColor={colors.muted}
        style={[styles.input, error ? styles.inputError : null]}
      />
      {error ? (
        <Text style={styles.fieldError} accessibilityLiveRegion="polite">
          Problem: {error}
        </Text>
      ) : hint ? (
        <Text style={styles.fieldHint}>{hint}</Text>
      ) : null}
    </View>
  );
}

export function Stepper({
  label,
  value,
  min,
  max,
  onChange,
  unit,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  unit: (value: number) => string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.stepper}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Fewer ${label.toLowerCase()}`}
          accessibilityState={{ disabled: value <= min }}
          disabled={value <= min}
          onPress={() => onChange(value - 1)}
          style={[styles.stepButton, value <= min && styles.stepDisabled]}
        >
          <Text style={styles.stepText}>−</Text>
        </Pressable>
        <View
          accessible
          accessibilityRole="adjustable"
          accessibilityLabel={label}
          accessibilityValue={{ min, max, now: value, text: unit(value) }}
          accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
          onAccessibilityAction={(e) => {
            if (e.nativeEvent.actionName === "increment" && value < max) onChange(value + 1);
            if (e.nativeEvent.actionName === "decrement" && value > min) onChange(value - 1);
          }}
          style={styles.stepValue}
        >
          <Text style={styles.stepValueText}>{unit(value)}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`More ${label.toLowerCase()}`}
          accessibilityState={{ disabled: value >= max }}
          disabled={value >= max}
          onPress={() => onChange(value + 1)}
          style={[styles.stepButton, value >= max && styles.stepDisabled]}
        >
          <Text style={styles.stepText}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

/**
 * Plan-level explanations from the backend (opening hours not checked, durations are defaults, ...).
 * Collapsed by default because there are several, but never hidden: product brief, section 7.
 */
export function PlanNotes({
  notes,
  defaultOpen = false,
}: {
  notes: { code: string; text: string }[];
  /** Shown open: for a note the user must read before accepting (Optimize, ADR 029). */
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (notes.length === 0) return null;
  return (
    <View style={styles.notes}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`About these plans, ${notes.length} notes`}
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((o) => !o)}
        style={styles.notesToggle}
      >
        <Text style={styles.notesToggleText}>
          {open ? "▾" : "▸"} About these plans ({notes.length})
        </Text>
      </Pressable>
      {open
        ? notes.map((n) => (
            <Text key={n.code} style={styles.noteText}>
              • {n.text}
            </Text>
          ))
        : null}
    </View>
  );
}

export function Card({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <View style={[styles.card, accent && styles.cardAccent]}>{children}</View>;
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingTop: spacing.xs, paddingBottom: spacing.md },

  headerTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  back: { minHeight: 40, justifyContent: "center", marginLeft: -spacing.md },
  // Pushed screens title themselves in the title size; only a root screen's title is display size.
  headerTitle: { ...type.title, color: colors.text },
  headerSubtitle: { ...type.caption, color: colors.muted, marginTop: spacing.xxs },

  compactHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  compactText: { flex: 1 },
  compactTitle: { ...type.heading, color: colors.text },
  compactSubtitle: { ...type.caption, color: colors.muted },

  notice: {
    padding: spacing.md,
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    borderRadius: radius.sm,
    marginBottom: spacing.sm,
  },
  noticeInfo: { backgroundColor: colors.surfaceMuted },
  noticeWarning: { backgroundColor: colors.warning },
  noticeError: { backgroundColor: colors.error },
  noticeText: { ...type.small, color: colors.text },
  noticeLabel: { fontWeight: "700" },

  centre: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
    gap: spacing.md,
  },
  stateTitle: { ...type.title, color: colors.text, textAlign: "center" },
  stateText: { ...type.body, color: colors.muted, textAlign: "center" },
  stateMeta: { ...type.caption, color: colors.muted },

  // Slim pills: 36 dp tall, with hit slop above and below for a 48 dp touch.
  chip: {
    minHeight: 36,
    paddingHorizontal: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.outline,
    backgroundColor: colors.surface,
  },
  chipSelected: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  chipText: { ...type.small, fontSize: 13, lineHeight: 18, color: colors.text, fontWeight: "600" },
  chipTextSelected: { color: colors.primary },

  field: { gap: spacing.xs },
  fieldLabel: { ...type.small, color: colors.text, fontWeight: "600" },
  input: {
    minHeight: TOUCH,
    borderWidth: 1.5,
    borderColor: colors.outline,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    color: colors.text,
    fontSize: type.body.fontSize,
  },
  inputError: { borderColor: colors.errorText },
  fieldHint: { ...type.caption, color: colors.muted },
  fieldError: { ...type.caption, color: colors.errorText, fontWeight: "600" },

  stepper: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  stepButton: {
    width: TOUCH,
    height: TOUCH,
    borderRadius: TOUCH / 2,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1.5,
    borderColor: colors.primary,
    backgroundColor: colors.surface,
  },
  stepDisabled: { opacity: 0.4 },
  stepText: { fontSize: 24, color: colors.primary, fontWeight: "600" },
  stepValue: { minWidth: 96, minHeight: TOUCH, justifyContent: "center", alignItems: "center" },
  stepValueText: { ...type.heading, color: colors.text },

  notes: { marginHorizontal: spacing.lg, marginBottom: spacing.sm, gap: spacing.xs },
  notesToggle: { minHeight: TOUCH, justifyContent: "center" },
  notesToggleText: { ...type.small, color: colors.link, fontWeight: "600" },
  noteText: { ...type.small, color: colors.muted },
  // Flat: a hairline under it, no box, no shadow (docs/design.md).
  card: {
    paddingVertical: spacing.lg,
    gap: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  cardAccent: { borderBottomColor: colors.primary },
});
