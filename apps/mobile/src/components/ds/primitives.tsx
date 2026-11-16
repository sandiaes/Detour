import { type ReactNode, useState } from "react";
import { Pressable, type PressableProps, ScrollView, StyleSheet, Text, View } from "react-native";

import {
  border,
  colors,
  opacity,
  radius,
  size as sizes,
  spacing,
  touchSlop,
  shadow,
  type,
  weight,
  card as cardStyle,
} from "../../theme";
import { Icon, type IconName, type IconSize } from "./Icon";

// The reusable pieces of the design system (docs/design.md, "Components"). Each meets the app's
// accessibility rules: a 48 dp touch target (drawn size plus hit slop), a spoken name for every
// control, and states told by words or marks as well as colour.

// ---- focus ---------------------------------------------------------------------------------------

/** The focus state of a pressable (keyboard, D-pad, switch access): a 2 dp green ring drawn as an
 * outline, so the layout does not move. Spread `focusProps` on the `Pressable`, add `ring` to its
 * style while `focused`. Exported for the bottom bar and the day pills. */
export function useFocusRing() {
  const [focused, setFocused] = useState(false);
  return {
    focused,
    focusProps: { onFocus: () => setFocused(true), onBlur: () => setFocused(false) },
    ring: focused ? focusRing : null,
  };
}

export const focusRing = {
  outlineWidth: border.thick,
  outlineColor: colors.selected,
  outlineOffset: -border.thick,
  outlineStyle: "solid" as const,
};

/** A `Pressable` that draws the focus ring: for every tappable thing that is not one of the shared
 * controls (a document row, a calendar day, a card). */
export function FocusPressable({ style, ...rest }: PressableProps) {
  const focus = useFocusRing();
  return (
    <Pressable
      {...rest}
      {...focus.focusProps}
      style={(state) => [typeof style === "function" ? style(state) : style, focus.ring]}
    />
  );
}

// ---- icon button ---------------------------------------------------------------------------------

export function IconButton({
  icon,
  label,
  onPress,
  variant = "plain",
  size = "md",
  color,
  disabled = false,
  hint,
  testID,
}: {
  icon: IconName;
  /** The spoken name; the button has no visible text. */
  label: string;
  onPress: () => void;
  /** plain: on the page; onImage: a dark disc on a photo; onMap: a white disc over a map. */
  variant?: "plain" | "onImage" | "onMap";
  /** md: 44 dp; sm: 36 dp, for headers, rows and map controls. Both touch at 48 dp. */
  size?: "md" | "sm";
  color?: string;
  disabled?: boolean;
  hint?: string;
  testID?: string;
}) {
  const focus = useFocusRing();
  const box = size === "sm" ? sizes.controlSm : sizes.control;
  const tint =
    color ?? (variant === "onImage" ? colors.onImage : disabled ? colors.muted : colors.text);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      {...focus.focusProps}
      testID={testID}
      hitSlop={touchSlop(box, size === "sm" ? spacing.xs : 0)}
      style={({ pressed }) => [
        styles.iconButton,
        { width: box, height: box, minHeight: box },
        variant === "onImage" && styles.iconButtonOnImage,
        variant === "onMap" && styles.iconButtonOnMap,
        pressed && (variant === "plain" ? styles.quietPressed : styles.pressed),
        disabled && styles.disabled,
        focus.ring,
      ]}
    >
      <Icon name={icon} size="md" color={tint} />
    </Pressable>
  );
}

// ---- badges --------------------------------------------------------------------------------------

export type BadgeTone = "neutral" | "primary" | "accent" | "onImage" | "danger" | "warning";

/** A small pill with a word in it ("Upcoming", "Best"). The word carries the meaning. */
export function Badge({
  label,
  tone = "neutral",
  icon,
}: {
  label: string;
  tone?: BadgeTone;
  icon?: IconName;
}) {
  const fg =
    tone === "primary"
      ? colors.primary
      : tone === "accent"
        ? colors.accentText
        : tone === "danger"
          ? colors.danger
          : tone === "warning"
            ? colors.warningText
            : colors.text;
  return (
    <View
      style={[
        styles.badge,
        tone === "primary" && { backgroundColor: colors.primarySoft },
        tone === "accent" && { backgroundColor: colors.accentSoft },
        tone === "danger" && { backgroundColor: colors.dangerSoft },
        tone === "warning" && { backgroundColor: colors.warning },
        tone === "onImage" && { backgroundColor: colors.surface },
      ]}
    >
      {icon ? <Icon name={icon} size="xs" color={fg} /> : null}
      <Text style={[styles.badgeText, { color: fg }]}>{label}</Text>
    </View>
  );
}

// ---- tabs and segmented control ------------------------------------------------------------------

export type TabItem<K extends string> = {
  key: K;
  label: string;
  count?: number;
  /** A fuller spoken name when the visible one repeats another control's ("Trip photos"). */
  accessibilityLabel?: string;
};

/** Underlined tabs: the sections of a page. Selected is shown by the colour, the weight and the
 * underline, and announced. */
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
  /** For more tabs than fit a phone's width. */
  scrollable?: boolean;
  /** 40 dp tabs for a tight header (a map). */
  compact?: boolean;
  testID?: string;
}) {
  const height = compact ? sizes.tabCompact : sizes.tab;
  const tabs = items.map((item) => {
    const active = item.key === value;
    const text = item.count !== undefined ? `${item.label} (${item.count})` : item.label;
    return (
      <TabButton
        key={item.key}
        item={item}
        text={text}
        active={active}
        height={height}
        auto={!scrollable}
        onPress={() => onChange(item.key)}
        testID={testID ? `${testID}-${item.key}` : undefined}
      />
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

function TabButton<K extends string>({
  item,
  text,
  active,
  height,
  auto,
  onPress,
  testID,
}: {
  item: TabItem<K>;
  text: string;
  active: boolean;
  height: number;
  auto: boolean;
  onPress: () => void;
  testID?: string;
}) {
  const focus = useFocusRing();
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityLabel={item.accessibilityLabel ?? text}
      accessibilityState={{ selected: active }}
      onPress={onPress}
      {...focus.focusProps}
      testID={testID}
      hitSlop={touchSlop(height)}
      style={[styles.tab, { minHeight: height }, auto && styles.tabAuto, focus.ring]}
    >
      <Text
        style={[styles.tabText, active && styles.tabTextActive]}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.85}
      >
        {text}
      </Text>
      <View style={[styles.tabLine, active && styles.tabLineActive]} />
    </Pressable>
  );
}

function Segment<K extends string>({
  item,
  active,
  inner,
  onPress,
  testID,
}: {
  item: TabItem<K>;
  active: boolean;
  inner: number;
  onPress: () => void;
  testID?: string;
}) {
  const focus = useFocusRing();
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityLabel={item.accessibilityLabel ?? item.label}
      accessibilityState={{ selected: active }}
      onPress={onPress}
      {...focus.focusProps}
      testID={testID}
      hitSlop={touchSlop(inner)}
      style={[styles.segment, { minHeight: inner }, active && styles.segmentActive, focus.ring]}
    >
      <Text
        style={[styles.segmentText, active && styles.segmentTextActive]}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.85}
      >
        {item.label}
      </Text>
    </Pressable>
  );
}

/** Two or three modes of one form ("Search, Address, Pin on map"). Announced as tabs, like the
 * platform's segmented controls. */
export function SegmentedControl<K extends string>({
  items,
  value,
  onChange,
  testID,
}: {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  testID?: string;
}) {
  const inner = sizes.control - 2 * spacing.xxs - 2 * border.thin;
  return (
    <View style={styles.segments} accessibilityRole="tablist" testID={testID}>
      {items.map((item) => (
        <Segment
          key={item.key}
          item={item}
          active={item.key === value}
          inner={inner}
          onPress={() => onChange(item.key)}
          testID={testID ? `${testID}-${item.key}` : undefined}
        />
      ))}
    </View>
  );
}

// ---- chips, radios and check boxes ---------------------------------------------------------------

/** A selectable pill (filters, kinds, a default value). Selected: a soft fill, a green outline and a
 * check mark, and announced. */
export function Chip({
  label,
  selected,
  onPress,
  accessibilityLabel,
  icon,
  disabled = false,
  testID,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  accessibilityLabel?: string;
  /** A line icon before the label; when selected the check mark takes its place. */
  icon?: IconName;
  disabled?: boolean;
  testID?: string;
}) {
  const shown: IconName | null = selected ? "check" : (icon ?? null);
  const focus = useFocusRing();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      {...focus.focusProps}
      testID={testID}
      hitSlop={touchSlop(sizes.controlSm)}
      style={({ pressed }) => [
        styles.chip,
        selected && styles.chipSelected,
        pressed && !selected && styles.quietPressed,
        disabled && styles.disabled,
        focus.ring,
      ]}
    >
      {shown ? (
        <Icon name={shown} size="sm" color={selected ? colors.selected : colors.text} />
      ) : null}
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

/** The mark of a one-of-many choice, drawn inside a row that carries the role and the name. */
export function Radio({ on }: { on: boolean }) {
  return (
    <View style={[styles.radio, on && styles.radioOn]}>
      {on ? <View style={styles.radioDot} /> : null}
    </View>
  );
}

/** The mark of a several-of-many choice, drawn inside a row that carries the role and the name. */
export function Checkbox({ on }: { on: boolean }) {
  return (
    <View style={[styles.check, on && styles.checkOn]}>
      {on ? <Icon name="check" size="xs" color={colors.onPrimary} /> : null}
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

/** A row of compact figures between hairlines: icon and number side by side, the word under them.
 * Each figure reads as one phrase ("5 cities"). */
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
          <View style={styles.statTop}>
            <Icon name={s.icon} size="sm" color={colors.primary} />
            <Text style={styles.statValue}>{s.value}</Text>
          </View>
          <Text style={styles.statLabel} numberOfLines={1}>
            {s.label}
          </Text>
        </View>
      ))}
    </View>
  );
}

// ---- section heading -------------------------------------------------------------------------------

/** The title of a section, with an optional action on the right. */
export function SectionHeader({ title, action }: { title: string; action?: ReactNode }) {
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

/**
 * The one list row (docs/design.md, "List row"): a leading mark, a title, up to two detail lines,
 * and a trailing chevron, badge or control, over a hairline. `regular` rows (56 dp, 15 pt title) are
 * menus and lists of things to open; `compact` rows (48 dp, 14 pt title) are options in a list or a
 * drop-down. A disabled row says why in words. `selected` tints the row and is announced.
 */
export function ListRow({
  icon,
  leading,
  title,
  detail,
  meta,
  onPress,
  trailing,
  density = "regular",
  inset = "gutter",
  selected,
  disabled = false,
  disabledLabel = "Coming later",
  danger = false,
  role = "button",
  checked,
  expanded,
  accessibilityLabel,
  accessibilityHint,
  divider = true,
  testID,
}: {
  /** A line icon in the leading column. */
  icon?: IconName;
  /** Any leading mark instead of an icon: a tile, a thumbnail, a number, a radio or a check box. */
  leading?: ReactNode;
  title: string;
  detail?: string | null;
  /** A second, quieter detail line. */
  meta?: string | null;
  onPress?: () => void;
  /** Replaces the chevron: a badge, a switch, an action. `null` shows nothing. */
  trailing?: ReactNode;
  density?: "regular" | "compact";
  /** gutter: 16 dp side padding (a full-width list); panel: 12 dp (inside a drop-down); none. */
  inset?: "gutter" | "panel" | "none";
  selected?: boolean;
  disabled?: boolean;
  /** The word shown on a disabled row instead of the chevron. */
  disabledLabel?: string;
  danger?: boolean;
  role?: "button" | "radio" | "checkbox";
  checked?: boolean;
  /** For a row that opens or closes something in place (a comparison): announced as expanded. */
  expanded?: boolean;
  accessibilityLabel?: string;
  accessibilityHint?: string;
  divider?: boolean;
  testID?: string;
}) {
  const compact = density === "compact";
  const spoken =
    accessibilityLabel ??
    [title, detail, meta, disabled ? disabledLabel : null].filter(Boolean).join(". ");
  const iconColor = danger ? colors.danger : disabled ? colors.muted : colors.primary;
  const end =
    trailing !== undefined ? (
      trailing
    ) : disabled ? (
      <Badge label={disabledLabel} />
    ) : selected && role === "button" ? (
      <Icon name="check" size="sm" color={colors.selected} />
    ) : onPress ? (
      <Icon name="chevronRight" size="sm" color={colors.muted} />
    ) : null;
  const minHeight = compact ? sizes.rowCompact : sizes.row;
  const focus = useFocusRing();
  return (
    <Pressable
      // A disabled row is still announced as a (dimmed) button, with the reason in its label.
      accessibilityRole={onPress || disabled ? role : undefined}
      accessibilityLabel={spoken}
      accessibilityHint={accessibilityHint}
      accessibilityState={{
        disabled: disabled || !onPress,
        ...(selected !== undefined ? { selected } : {}),
        ...(checked !== undefined ? { checked } : {}),
        ...(expanded !== undefined ? { expanded } : {}),
      }}
      accessible
      disabled={disabled || !onPress}
      onPress={onPress}
      {...focus.focusProps}
      testID={testID}
      style={({ pressed }) => [
        focus.ring,
        styles.row,
        { minHeight },
        inset === "gutter" && styles.rowGutter,
        inset === "panel" && styles.rowPanel,
        divider && styles.rowDivider,
        selected && styles.rowSelected,
        pressed && styles.quietPressed,
      ]}
    >
      {icon ? (
        <View style={styles.rowIcon}>
          <Icon name={icon} size="md" color={iconColor} />
        </View>
      ) : (
        leading
      )}
      <View style={styles.rowText}>
        <Text
          style={[
            compact ? styles.rowTitleCompact : styles.rowTitle,
            danger && { color: colors.danger },
            disabled && styles.rowTitleDisabled,
          ]}
        >
          {title}
        </Text>
        {detail ? <Text style={styles.rowDetail}>{detail}</Text> : null}
        {meta ? <Text style={styles.rowDetail}>{meta}</Text> : null}
      </View>
      {end}
    </Pressable>
  );
}

/**
 * The header of a group of rows that can be folded away (the continents on the Regions screen), the
 * top of a `Card` that holds the group: its name, a quiet summary and a chevron. A tap opens or
 * closes the group; the state is announced as expanded or collapsed.
 */
export function GroupHeader({
  title,
  summary,
  expanded,
  onToggle,
  testID,
}: {
  title: string;
  summary?: string;
  expanded: boolean;
  onToggle: () => void;
  testID?: string;
}) {
  const focus = useFocusRing();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[title, summary].filter(Boolean).join(". ")}
      accessibilityHint={expanded ? "Hides the group" : "Shows the group"}
      accessibilityState={{ expanded }}
      onPress={onToggle}
      {...focus.focusProps}
      testID={testID}
      style={({ pressed }) => [
        styles.groupHeader,
        pressed && styles.groupHeaderPressed,
        focus.ring,
      ]}
    >
      <Text accessibilityRole="header" style={styles.groupHeaderTitle}>
        {title}
      </Text>
      {summary ? <Text style={styles.groupHeaderSummary}>{summary}</Text> : null}
      <Icon name={expanded ? "up" : "down"} size="sm" color={colors.muted} />
    </Pressable>
  );
}

/** A group of rows divided by hairlines: no card, no shadow. */
export function RowGroup({ children }: { children: ReactNode }) {
  return <View style={styles.group}>{children}</View>;
}

/** A fact: a small label over its value, over a hairline. */
export function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.info} accessible accessibilityLabel={`${label}: ${value}`}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

/** A quiet line with a small icon and no label: when it is, where, how much. */
export function MetaLine({
  icon,
  text,
  tone = "muted",
}: {
  icon: IconName;
  text: string;
  tone?: "muted" | "text" | "danger";
}) {
  const colour = tone === "danger" ? colors.danger : tone === "text" ? colors.text : colors.muted;
  return (
    <View style={styles.metaLine} accessible accessibilityLabel={text}>
      <Icon name={icon} size="sm" color={colour} />
      <Text style={[styles.metaText, { color: colour }]}>{text}</Text>
    </View>
  );
}

/** A list of short lines with bullets (reasons, notes, differences). */
export function Bullets({ items, tone = "text" }: { items: string[]; tone?: "text" | "muted" }) {
  return (
    <View style={styles.bullets}>
      {items.map((item) => (
        <View key={item} style={styles.bullet} accessible accessibilityLabel={item}>
          <View style={[styles.bulletDot, tone === "muted" && styles.bulletDotMuted]} />
          <Text style={[styles.bulletText, tone === "muted" && styles.bulletTextMuted]}>
            {item}
          </Text>
        </View>
      ))}
    </View>
  );
}

// ---- cards, sections and tiles -------------------------------------------------------------------

/** The card (docs/design.md): white, 16 dp corners, a hairline and a soft shadow, for a thing that
 * is picked up and opened. One look everywhere. */
export function Card({
  children,
  padded = true,
  testID,
}: {
  children: ReactNode;
  /** False for a card whose first child (a cover) runs to its edges. */
  padded?: boolean;
  testID?: string;
}) {
  return (
    <View style={[styles.card, padded && styles.cardPadded]} testID={testID}>
      {children}
    </View>
  );
}

/** A flat section of a settings-like page: a hairline above, a title, its text and actions. No box. */
export function Section({
  title,
  children,
  testID,
}: {
  title?: string;
  children: ReactNode;
  testID?: string;
}) {
  return (
    <View style={styles.section} testID={testID}>
      {title ? <SectionHeader title={title} /> : null}
      {children}
    </View>
  );
}

const TILE = {
  sm: { box: 32, radius: radius.sm, icon: "sm" as IconSize },
  md: { box: sizes.tile, radius: radius.md, icon: "md" as IconSize },
  lg: { box: sizes.thumb, radius: radius.md, icon: "lg" as IconSize },
};

/** An icon on a soft tone: what kind a thing is (a document, a way to add, a visited place). */
export function Tile({
  icon,
  fg,
  bg,
  size = "md",
}: {
  icon: IconName;
  fg: string;
  bg: string;
  size?: keyof typeof TILE;
}) {
  const t = TILE[size];
  return (
    <View
      style={[
        styles.tile,
        { width: t.box, height: t.box, borderRadius: t.radius, backgroundColor: bg },
      ]}
    >
      <Icon name={icon} size={t.icon} color={fg} />
    </View>
  );
}

export type MarkKind = "sight" | "eat" | "transport" | "city" | "quiet";

const MARK_SIZE = { list: sizes.mark, map: sizes.marker, selected: sizes.markerSelected, key: 14 };

/**
 * The mark of a stop, shared by the day list, the map and the map key: sights are round and green,
 * places to eat rounded squares in orange, travel and cities navy rounded squares; a day colour can
 * replace the fill. The words beside it always say the kind too.
 */
export function StopMark({
  kind,
  label,
  icon,
  size = "list",
  color,
  selected = false,
}: {
  kind: MarkKind;
  /** A number in the mark. */
  label?: string | number;
  icon?: IconName;
  size?: keyof typeof MARK_SIZE;
  /** A day's colour instead of the kind's. */
  color?: string;
  selected?: boolean;
}) {
  const box = selected ? MARK_SIZE.selected : MARK_SIZE[size];
  const square = kind === "eat" || kind === "transport" || kind === "city";
  const fill = selected
    ? colors.markerSelected
    : (color ??
      (kind === "eat"
        ? colors.eat
        : kind === "transport" || kind === "city"
          ? colors.ink
          : kind === "quiet"
            ? colors.surfaceMuted
            : colors.marker));
  const onMap = size === "map" || selected;
  return (
    <View
      style={[
        styles.mark,
        {
          width: box,
          height: box,
          borderRadius: square ? Math.round(box * 0.3) : box / 2,
          backgroundColor: fill,
        },
        onMap && styles.markOnMap,
      ]}
    >
      {label !== undefined ? (
        <Text style={styles.markText} maxFontSizeMultiplier={1.3}>
          {label}
        </Text>
      ) : icon ? (
        <Icon name={icon} size="xs" color={kind === "quiet" ? colors.muted : colors.onPrimary} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: opacity.pressed },
  quietPressed: { backgroundColor: colors.surfaceMuted },
  disabled: { opacity: opacity.disabled },

  iconButton: { borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  iconButtonOnImage: { backgroundColor: colors.imageButton },
  iconButtonOnMap: { backgroundColor: colors.surface, ...shadow.floating },

  badge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xxs,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  badgeText: { ...type.micro, fontWeight: weight.semibold },

  tabBar: { borderBottomWidth: border.hairline, borderBottomColor: colors.border },
  tabScroll: { paddingHorizontal: spacing.lg, gap: spacing.lg },
  // Equal gutters at both edges, the same space between the labels.
  tabRow: { flexDirection: "row", justifyContent: "space-between", gap: 0 },
  tab: { justifyContent: "flex-end", alignItems: "center" },
  tabAuto: { paddingHorizontal: spacing.xs, flexShrink: 1 },
  tabText: {
    ...type.label,
    color: colors.muted,
    fontWeight: weight.medium,
    paddingBottom: spacing.sm,
  },
  tabTextActive: { color: colors.selected, fontWeight: weight.semibold },
  tabLine: {
    height: border.thick,
    alignSelf: "stretch",
    borderRadius: radius.pill,
    backgroundColor: "transparent",
  },
  tabLineActive: { backgroundColor: colors.selected },

  segments: {
    flexDirection: "row",
    padding: spacing.xxs,
    gap: spacing.xxs,
    borderRadius: radius.md,
    borderWidth: border.thin,
    borderColor: colors.border,
    backgroundColor: colors.surfaceMuted,
  },
  segment: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: border.thin,
    borderColor: "transparent",
  },
  segmentActive: {
    backgroundColor: colors.surface,
    borderColor: colors.selected,
  },
  segmentText: { ...type.label, color: colors.muted, fontWeight: weight.medium },
  segmentTextActive: { color: colors.selected, fontWeight: weight.semibold },

  chip: {
    minHeight: sizes.controlSm,
    paddingHorizontal: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: border.thin,
    borderColor: colors.outline,
    backgroundColor: colors.surface,
  },
  chipSelected: { backgroundColor: colors.selectedSoft, borderColor: colors.selected },
  chipText: { ...type.caption, color: colors.text, fontWeight: weight.semibold },
  chipTextSelected: { color: colors.selected },

  radio: {
    width: sizes.radio,
    height: sizes.radio,
    borderRadius: radius.pill,
    borderWidth: border.thick,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  radioOn: { borderColor: colors.selected },
  radioDot: { width: 10, height: 10, borderRadius: radius.pill, backgroundColor: colors.selected },
  check: {
    width: sizes.radio,
    height: sizes.radio,
    borderRadius: radius.xs,
    borderWidth: border.thick,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  checkOn: { backgroundColor: colors.selected, borderColor: colors.selected },

  statRow: {
    flexDirection: "row",
    borderTopWidth: border.hairline,
    borderBottomWidth: border.hairline,
    borderColor: colors.border,
  },
  stat: { flex: 1, alignItems: "center", paddingVertical: spacing.sm },
  statTop: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  statDivider: { borderLeftWidth: border.hairline, borderLeftColor: colors.border },
  statValue: { ...type.headline, color: colors.text },
  statLabel: { ...type.caption, color: colors.muted },

  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  sectionTitle: { ...type.headline, color: colors.text, flexShrink: 1 },

  group: { borderTopWidth: border.hairline, borderTopColor: colors.border },
  groupHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: sizes.row,
    paddingHorizontal: spacing.lg,
  },
  groupHeaderPressed: { backgroundColor: colors.surfaceMuted },
  groupHeaderTitle: { ...type.headline, color: colors.text, flex: 1 },
  groupHeaderSummary: { ...type.caption, color: colors.muted },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  rowGutter: { paddingHorizontal: spacing.lg },
  rowPanel: { paddingHorizontal: spacing.md },
  rowDivider: { borderBottomWidth: border.hairline, borderBottomColor: colors.border },
  rowSelected: { backgroundColor: colors.selectedSoft },
  rowIcon: { width: 24, alignItems: "center", justifyContent: "center" },
  rowText: { flex: 1, gap: spacing.xxs },
  rowTitle: { ...type.body, fontWeight: weight.semibold, color: colors.text },
  rowTitleCompact: { ...type.label, fontWeight: weight.semibold, color: colors.text },
  rowTitleDisabled: { color: colors.muted },
  rowDetail: { ...type.caption, color: colors.muted },

  info: {
    gap: spacing.xxs,
    paddingVertical: spacing.sm,
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  infoLabel: { ...type.caption, color: colors.muted },
  infoValue: { ...type.label, color: colors.text },
  metaLine: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  metaText: { ...type.label, flex: 1 },
  bullets: { gap: spacing.xs },
  bullet: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  bulletDot: {
    width: 4,
    height: 4,
    borderRadius: radius.pill,
    marginTop: spacing.sm,
    backgroundColor: colors.text,
  },
  bulletDotMuted: { backgroundColor: colors.muted },
  bulletText: { ...type.label, color: colors.text, flex: 1 },
  bulletTextMuted: { color: colors.muted },

  card: { ...cardStyle, gap: spacing.sm, overflow: "hidden" },
  cardPadded: { padding: spacing.md },
  section: {
    gap: spacing.sm,
    paddingTop: spacing.lg,
    borderTopWidth: border.hairline,
    borderTopColor: colors.border,
  },
  tile: { alignItems: "center", justifyContent: "center" },

  mark: { alignItems: "center", justifyContent: "center" },
  markOnMap: { borderWidth: border.thick, borderColor: colors.onPrimary, ...shadow.card },
  markText: { ...type.micro, fontWeight: weight.semibold, color: colors.onPrimary },
});
