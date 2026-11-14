import type { ReactNode } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { TOUCH, colors, radius, shadow, spacing, type } from "../../theme";
import { Icon, type IconName } from "./Icon";

// The reusable pieces of the redesign (ADR 021). Each one meets the app's accessibility rules:
// 48 dp touch targets, a spoken name for every control, and states told by words or marks as well
// as colour.

// ---- icon button ---------------------------------------------------------------------------------

export function IconButton({
  icon,
  label,
  onPress,
  onImage = false,
  compact = false,
  hint,
  testID,
}: {
  icon: IconName;
  /** The spoken name; the button has no visible text. */
  label: string;
  onPress: () => void;
  /** On a cover picture: a dark translucent disc and a white icon. */
  onImage?: boolean;
  /** A shorter button (40 x 36) for tight headers; its hit slop keeps the touch at 48 dp. */
  compact?: boolean;
  hint?: string;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      onPress={onPress}
      testID={testID}
      hitSlop={compact ? { top: 6, bottom: 6, left: 4, right: 4 } : undefined}
      style={({ pressed }) => [
        styles.iconButton,
        compact && styles.iconButtonCompact,
        onImage && styles.iconButtonOnImage,
        pressed && styles.pressed,
      ]}
    >
      <Icon name={icon} color={onImage ? colors.onImage : colors.text} />
    </Pressable>
  );
}

// ---- badges --------------------------------------------------------------------------------------

export type BadgeTone = "neutral" | "primary" | "accent" | "solid";

/** A small pill with a word in it ("Upcoming", "Past"). The word carries the meaning. */
export function Badge({ label, tone = "neutral" }: { label: string; tone?: BadgeTone }) {
  return (
    <View
      style={[
        styles.badge,
        tone === "primary" && { backgroundColor: colors.primarySoft },
        tone === "accent" && { backgroundColor: colors.accentSoft },
        tone === "solid" && { backgroundColor: colors.surface },
      ]}
    >
      <Text
        style={[
          styles.badgeText,
          tone === "primary" && { color: colors.primary },
          tone === "accent" && { color: colors.accentText },
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

// ---- tabs ----------------------------------------------------------------------------------------

export type TabItem<K extends string> = {
  key: K;
  label: string;
  count?: number;
  /** A fuller spoken name when the visible one repeats another control's ("Trip photos"). */
  accessibilityLabel?: string;
};

/** Underlined tabs. Selected is shown by the underline, bold text and the announced state. */
export function Tabs<K extends string>({
  items,
  value,
  onChange,
  scrollable = false,
  compact = false,
  testID,
}: {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  /** For more tabs than fit a phone's width (the trip's five tabs). */
  scrollable?: boolean;
  /** Shorter tabs (40 dp, plus hit slop) for the map's tight header. */
  compact?: boolean;
  testID?: string;
}) {
  const tabs = items.map((item) => {
    const active = item.key === value;
    const text = item.count !== undefined ? `${item.label} (${item.count})` : item.label;
    return (
      <Pressable
        key={item.key}
        accessibilityRole="tab"
        accessibilityLabel={item.accessibilityLabel ?? text}
        accessibilityState={{ selected: active }}
        onPress={() => onChange(item.key)}
        testID={testID ? `${testID}-${item.key}` : undefined}
        hitSlop={compact ? { top: 4, bottom: 4 } : undefined}
        style={[styles.tab, compact && styles.tabCompact, !scrollable && styles.tabFill]}
      >
        <Text style={[styles.tabText, active && styles.tabTextActive]} numberOfLines={1}>
          {text}
        </Text>
        <View style={[styles.tabLine, active && styles.tabLineActive]} />
      </Pressable>
    );
  });
  return (
    <View style={styles.tabBar} accessibilityRole="tablist" testID={testID}>
      {scrollable ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.tabScroll}
        >
          {tabs}
        </ScrollView>
      ) : (
        <View style={[styles.tabScroll, styles.tabRow]}>{tabs}</View>
      )}
    </View>
  );
}

// ---- statistics ----------------------------------------------------------------------------------

export type Stat = {
  key: string;
  icon: IconName;
  value: number | string;
  label: string;
  spoken?: string;
};

/** A row of compact figures. Each tile reads as one phrase ("5 cities"). */
export function StatRow({ stats }: { stats: Stat[] }) {
  return (
    <View style={styles.statRow}>
      {stats.map((s, i) => (
        <View
          key={s.key}
          style={[styles.stat, i > 0 && styles.statDivider]}
          accessible
          accessibilityLabel={s.spoken ?? `${s.value} ${s.label.toLowerCase()}`}
        >
          <Icon name={s.icon} size={18} color={colors.primary} />
          <Text style={styles.statValue}>{s.value}</Text>
          <Text style={styles.statLabel} numberOfLines={1}>
            {s.label}
          </Text>
        </View>
      ))}
    </View>
  );
}

// ---- section heading -------------------------------------------------------------------------------

export function SectionTitle({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <View style={styles.sectionHead}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        {title}
      </Text>
      {action}
    </View>
  );
}

// ---- list rows -----------------------------------------------------------------------------------

/** A menu row: icon, title, a line of detail and a chevron. Disabled rows say why in words. */
export function ListRow({
  icon,
  title,
  detail,
  onPress,
  disabled = false,
  disabledLabel = "Coming later",
  danger = false,
  testID,
}: {
  icon: IconName;
  title: string;
  detail?: string;
  onPress?: () => void;
  disabled?: boolean;
  /** The word shown on a disabled row instead of the chevron. */
  disabledLabel?: string;
  danger?: boolean;
  testID?: string;
}) {
  const spoken = [title, detail, disabled ? disabledLabel : null].filter(Boolean).join(". ");
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={spoken}
      accessibilityState={{ disabled }}
      disabled={disabled || !onPress}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      <View style={[styles.rowIcon, disabled && styles.rowIconDisabled]}>
        <Icon
          name={icon}
          color={danger ? colors.errorText : disabled ? colors.muted : colors.primary}
        />
      </View>
      <View style={styles.rowText}>
        <Text style={[styles.rowTitle, danger && { color: colors.errorText }]}>{title}</Text>
        {detail ? <Text style={styles.rowDetail}>{detail}</Text> : null}
      </View>
      {disabled ? (
        <Badge label={disabledLabel} />
      ) : (
        <Icon name="chevronRight" size={18} color={colors.muted} />
      )}
    </Pressable>
  );
}

/** A group of rows divided by hairlines: no card, no shadow. */
export function RowGroup({ children }: { children: ReactNode }) {
  return <View style={styles.group}>{children}</View>;
}

// ---- a feature that is planned but not built ---------------------------------------------------

/** Says plainly that a part of the design is not built yet, and what it will do. */
export function PlannedFeature({
  icon,
  title,
  text,
  testID,
}: {
  icon: IconName;
  title: string;
  text: string;
  testID?: string;
}) {
  return (
    <View
      style={styles.planned}
      testID={testID}
      accessible
      accessibilityLabel={`${title}. ${text}`}
    >
      <View style={styles.plannedIcon}>
        <Icon name={icon} size={28} color={colors.primary} />
      </View>
      <Text style={styles.plannedTitle}>{title}</Text>
      <Text style={styles.plannedText}>{text}</Text>
      <Badge label="Not built yet" />
    </View>
  );
}

// ---- bottom sheet ----------------------------------------------------------------------------------

/** A sheet of actions that slides up from the bottom; tapping outside or Back closes it. */
export function Sheet({
  visible,
  title,
  onClose,
  children,
}: {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.sheetRoot}>
        <Pressable
          style={styles.backdrop}
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={onClose}
        />
        <View style={[styles.sheet, { paddingBottom: spacing.lg + insets.bottom }]}>
          <View style={styles.grabber} />
          <View style={styles.sheetHead}>
            <Text accessibilityRole="header" style={styles.sheetTitle}>
              {title}
            </Text>
            <IconButton icon="close" label="Close" onPress={onClose} />
          </View>
          {children}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.75 },

  iconButton: {
    width: TOUCH,
    height: TOUCH,
    minHeight: TOUCH,
    borderRadius: TOUCH / 2,
    alignItems: "center",
    justifyContent: "center",
  },
  iconButtonCompact: { width: 40, height: 36, minHeight: 36, borderRadius: 18 },
  iconButtonOnImage: { backgroundColor: colors.imageButton },

  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xxs + 1,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  badgeText: { ...type.caption, fontWeight: "600", color: colors.text },

  tabBar: { borderBottomWidth: 1, borderBottomColor: colors.border },
  tabScroll: { paddingHorizontal: spacing.lg, gap: spacing.lg },
  tabRow: { flexDirection: "row" },
  tab: { minHeight: TOUCH, justifyContent: "flex-end", alignItems: "center" },
  tabFill: { flex: 1 },
  tabCompact: { minHeight: 40 },
  tabText: {
    ...type.small,
    color: colors.muted,
    fontWeight: "500",
    paddingBottom: spacing.sm,
  },
  tabTextActive: { color: colors.text, fontWeight: "700" },
  tabLine: { height: 2.5, alignSelf: "stretch", borderRadius: 2, backgroundColor: "transparent" },
  tabLineActive: { backgroundColor: colors.text },

  // Flat: figures separated by hairlines, no boxes (docs/design.md).
  statRow: {
    flexDirection: "row",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  stat: {
    flex: 1,
    alignItems: "center",
    gap: spacing.xxs,
    paddingVertical: spacing.md,
  },
  statDivider: { borderLeftWidth: StyleSheet.hairlineWidth, borderLeftColor: colors.border },
  statValue: { ...type.title, color: colors.text },
  statLabel: { ...type.caption, color: colors.muted },

  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  sectionTitle: { ...type.heading, color: colors.text },

  group: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  row: {
    minHeight: TOUCH + 8,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowIcon: { width: 32, alignItems: "center", justifyContent: "center" },
  rowIconDisabled: {},
  rowText: { flex: 1, gap: spacing.xxs },
  rowTitle: { ...type.body, fontWeight: "600", color: colors.text },
  rowDetail: { ...type.small, color: colors.muted },

  planned: {
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  plannedIcon: { alignItems: "center", justifyContent: "center" },
  plannedTitle: { ...type.heading, color: colors.text, textAlign: "center" },
  plannedText: { ...type.small, color: colors.muted, textAlign: "center" },

  sheetRoot: { flex: 1, justifyContent: "flex-end" },
  backdrop: {
    ...StyleSheet.absoluteFill,
    minHeight: TOUCH,
    backgroundColor: "rgba(20, 36, 58, 0.35)",
  },
  sheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
    ...shadow.raised,
  },
  grabber: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    marginTop: spacing.sm,
    backgroundColor: colors.border,
  },
  sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sheetTitle: { ...type.title, color: colors.text },
});
