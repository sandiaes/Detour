import type { ClientConfig, Day, Item } from "@detour/shared";
import { type ComponentRef, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { ItemActions } from "../../data/itemActions";
import {
  type DayRow,
  STOP_KIND_LABEL,
  buildDayRows,
  confidenceLabel,
  dayTotals,
  isEatKind,
  modeLabel,
  stopKind,
  transportPoint,
} from "../../domain/itinerary";
import { TOUCH, colors, radius, shadow, spacing, type } from "../../theme";
import {
  formatClock,
  formatCuisines,
  formatDate,
  formatMeters,
  formatMinutes,
  formatSeconds,
  pluralise,
} from "../../util/format";
import { Button } from "../Button";
import { Icon } from "../ds/Icon";
import { EmptyState } from "../ui";
import { ItineraryMap } from "../ItineraryMap";

// One day of a plan (ADR 021, step 3): a day selector, the day's stops in time order, and the map.
// The list and the map share one selection: choosing a stop in either highlights it in both.

export const MEAL_LABEL = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  snack: "Afternoon snack",
  dinner: "Dinner",
} as const;

export function dayTitle(day: Day): string {
  return day.date
    ? `Day ${day.day_index} · ${formatDate(day.date, false)}`
    : `Day ${day.day_index}`;
}

export function dayTotalsText(day: Day): string {
  const t = dayTotals(day);
  if (t.visits === 0 && t.meals === 0) return "Nothing planned";
  const meals = t.meals > 0 ? ` · ${pluralise(t.meals, "meal")}` : "";
  return `${pluralise(t.visits, "visit")}${meals} · ${formatMinutes(t.visitMinutes)} at the sights · ${formatSeconds(t.travelSeconds)} travelling`;
}

/** The drive from the previous base city that starts the day, as one line. */
export function arrivalText(day: Day): string | null {
  const a = day.arrival;
  if (!a) return null;
  const from = a.from_base_city_name ? ` from ${a.from_base_city_name}` : "";
  return `${a.mode === "walk" ? "Walk" : "Drive"}${from} · ${formatSeconds(a.seconds)} · ${formatMeters(a.meters)}`;
}

/** "Lunch · Restaurant · 1 h" or "Attraction · 2 h": what a stop is, in words, and how long. */
export function stopSummary(item: Item): string {
  const kind = stopKind(item);
  const parts: string[] = [];
  if (item.type === "meal" && item.meal_type) parts.push(MEAL_LABEL[item.meal_type]);
  if (item.type === "free_time") parts.push("Free time");
  else parts.push(STOP_KIND_LABEL[kind]);
  parts.push(formatMinutes(item.duration_minutes));
  return parts.join(" · ");
}

/** The sentence a screen reader hears for a stop. */
export function stopSentence(item: Item, ordinal: number | null): string {
  const start = formatClock(item.start_time);
  const end = formatClock(item.end_time);
  const meal = item.type === "meal";
  const source =
    item.duration_source === "user"
      ? "set by you"
      : meal
        ? "typical meal length"
        : "typical visit length";
  const kind =
    meal && item.meal_type
      ? MEAL_LABEL[item.meal_type]
      : item.type === "free_time"
        ? "Free time"
        : null;
  const cuisine = meal ? formatCuisines(item.restaurant?.cuisines) : null;
  const when = start ? (end ? `${start} to ${end}` : start) : "Time not set";
  const reasons = item.reason_texts.join(" ");
  const tags = [item.locked ? "Locked" : null, item.origin === "user" ? "Added by you" : null]
    .filter(Boolean)
    .join(" · ");
  return (
    `${ordinal ? `Stop ${ordinal}. ` : ""}${item.type === "free_time" ? "" : `${STOP_KIND_LABEL[stopKind(item)]}. `}${kind ? `${kind}. ` : ""}${item.display_name}. ` +
    `${tags ? `${tags}. ` : ""}${cuisine ? `${cuisine}. ` : ""}${when}. ` +
    `${formatMinutes(item.duration_minutes)}, ${source}.${reasons ? ` Why: ${reasons}` : ""}`
  );
}

// ---- day selector ----------------------------------------------------------------------------

export function DayStrip({
  days,
  value,
  onChange,
}: {
  days: Day[];
  value: number;
  onChange: (dayIndex: number) => void;
}) {
  return (
    <ScrollView
      horizontal
      style={styles.strip}
      contentContainerStyle={styles.stripContent}
      showsHorizontalScrollIndicator={false}
      accessibilityRole="tablist"
    >
      {days.map((d) => {
        const active = d.day_index === value;
        const date = d.date ? formatDate(d.date, false) : null;
        return (
          <Pressable
            key={d.id}
            accessibilityRole="tab"
            accessibilityLabel={`Day ${d.day_index}${date ? `, ${date}` : ""}`}
            accessibilityState={{ selected: active }}
            onPress={() => onChange(d.day_index)}
            style={[styles.dayPill, active && styles.dayPillActive]}
            testID={`day-tab-${d.day_index}`}
          >
            <Text style={[styles.dayPillTitle, active && styles.dayPillTextActive]}>
              Day {d.day_index}
            </Text>
            {date ? (
              <Text style={[styles.dayPillDate, active && styles.dayPillTextActive]}>{date}</Text>
            ) : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

// ---- rows ------------------------------------------------------------------------------------

function DayHead({ day, showBase }: { day: Day; showBase: boolean }) {
  const base = showBase && day.base_city_name ? day.base_city_name : null;
  return (
    <View
      style={styles.dayHead}
      accessible
      accessibilityRole="header"
      accessibilityLabel={`${dayTitle(day)}. ${base ? `Based in ${base}. ` : ""}${dayTotalsText(day)}.`}
    >
      <View style={styles.dayHeadTop}>
        <Text style={styles.dayHeadTitle}>{dayTitle(day)}</Text>
        {base ? (
          <View style={styles.basePill}>
            <Icon name="city" size={14} color={colors.primary} />
            <Text style={styles.basePillText}>{base}</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.meta}>{dayTotalsText(day)}</Text>
    </View>
  );
}

function Tag({ routed }: { routed: boolean }) {
  // The label is a word, and the border differs (solid or dashed): not colour alone.
  return (
    <Text style={[styles.tag, routed ? styles.tagRouted : styles.tagEstimated]}>
      {routed ? "Routed" : "Estimated"}
    </Text>
  );
}

function ArrivalRow({
  day,
  selectable,
  selected,
  onSelect,
}: {
  day: Day;
  selectable: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const text = arrivalText(day) as string;
  const routed = day.arrival?.confidence === "routed";
  const label =
    `Transport. ${text}, ${routed ? "routed." : "estimated, a straight-line estimate and not a measured route."}` +
    (day.base_city_name ? ` Arrives in ${day.base_city_name}.` : "");
  return (
    <View style={styles.row}>
      <View style={styles.timeCol}>
        <Text style={styles.time}>Start</Text>
      </View>
      <Pressable
        accessibilityRole={selectable ? "button" : undefined}
        accessibilityLabel={label}
        accessibilityHint={selectable ? "Highlights it on the map" : undefined}
        accessibilityState={selectable ? { selected } : undefined}
        accessible
        disabled={!selectable}
        onPress={onSelect}
        style={[styles.card, styles.cardRow, selected && styles.cardSelected]}
        testID={`arrival-${day.day_index}`}
      >
        <View style={[styles.disc, styles.discTransport]}>
          <Icon name="transport" size={18} color={colors.onPrimary} />
        </View>
        <View style={styles.cardText}>
          <Text style={styles.title}>
            {day.base_city_name ? `To ${day.base_city_name}` : "Travel"}
          </Text>
          <Text style={styles.meta}>{text}</Text>
          <Tag routed={routed} />
        </View>
      </Pressable>
    </View>
  );
}

export function StopRow({
  item,
  ordinal,
  selected,
  onSelect,
  onDetails,
  actions,
}: {
  item: Item;
  ordinal: number | null;
  selected: boolean;
  onSelect: () => void;
  onDetails?: () => void;
  actions?: ItemActions;
}) {
  const start = formatClock(item.start_time);
  const end = formatClock(item.end_time);
  const stop = stopKind(item);
  const eat = isEatKind(stop);
  const meal = item.type === "meal";
  const source =
    item.duration_source === "user"
      ? "set by you"
      : meal
        ? "typical meal length"
        : "typical visit length";
  const tags = [item.locked ? "Locked" : null, item.origin === "user" ? "Added by you" : null]
    .filter(Boolean)
    .join(" · ");
  const busy = actions?.busyId === item.id;
  return (
    <View style={styles.row}>
      <View style={styles.timeCol}>
        <Text style={styles.time}>{start ?? "–"}</Text>
        {end ? <Text style={styles.timeEnd}>{end}</Text> : null}
      </View>
      <View style={[styles.card, eat && styles.cardEat, selected && styles.cardSelected]}>
        <View style={styles.cardRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={stopSentence(item, ordinal)}
            accessibilityHint={ordinal ? "Highlights it on the map" : undefined}
            accessibilityState={{ selected }}
            onPress={onSelect}
            style={styles.select}
            testID={`stop-${item.id}`}
          >
            {ordinal ? (
              // Sights are round and teal, places to eat square and orange, and the words below
              // say it too: never colour alone.
              <View style={[styles.disc, eat && styles.discEat]}>
                <Text style={styles.discText} maxFontSizeMultiplier={1.3}>
                  {ordinal}
                </Text>
              </View>
            ) : (
              <View style={[styles.disc, styles.discQuiet]}>
                <Icon name="clock" size={18} color={colors.muted} />
              </View>
            )}
            <View style={styles.cardText}>
              <Text style={styles.title}>{item.display_name}</Text>
              <Text
                testID={`kind-${stop}`}
                style={[styles.kind, eat ? styles.kindEat : styles.kindSight]}
              >
                {stopSummary(item)}
              </Text>
              {meal ? (
                <Text style={styles.meta}>{formatCuisines(item.restaurant?.cuisines)}</Text>
              ) : null}
              {tags ? <Text style={styles.tags}>{tags}</Text> : null}
            </View>
          </Pressable>
          {onDetails ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Details of ${item.display_name}`}
              onPress={onDetails}
              style={styles.chevron}
              testID={`details-${item.id}`}
            >
              <Icon name="chevronRight" size={20} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
        {selected ? (
          <View style={styles.expanded} accessibilityLiveRegion="polite">
            <Text style={styles.meta}>
              {formatMinutes(item.duration_minutes)} · {source}
            </Text>
            {item.reason_texts.map((r) => (
              <Text key={r} style={styles.reason}>
                {r}
              </Text>
            ))}
            {actions && item.type === "visit" ? (
              <View style={styles.actions}>
                <Button
                  label={item.locked ? "Unlock" : "Lock"}
                  variant="secondary"
                  disabled={busy}
                  accessibilityLabel={`${item.locked ? "Unlock" : "Lock"} ${item.display_name}`}
                  hint={
                    item.locked
                      ? "Recalculations may move it again."
                      : "Keeps its day and time when the plan is recalculated."
                  }
                  onPress={() => actions.onToggleLock(item)}
                />
                <Button
                  label="Remove"
                  variant="secondary"
                  disabled={busy || item.locked}
                  accessibilityLabel={`Remove ${item.display_name}`}
                  hint={item.locked ? "Unlock it first." : "Shows what would change first."}
                  onPress={() => actions.onRemove(item)}
                />
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

export function TransferRow({ row }: { row: Extract<DayRow, { kind: "transfer" }> }) {
  const { transfer, to } = row;
  const routed = transfer.confidence === "routed";
  const text = `${modeLabel(transfer.mode)} · ${formatSeconds(transfer.seconds)} · ${formatMeters(transfer.meters)}`;
  const label =
    `${modeLabel(transfer.mode)} ${to ? `to ${to.display_name}` : "to the next stop"}, ` +
    `${formatSeconds(transfer.seconds)}, ${formatMeters(transfer.meters)}, ${confidenceLabel(transfer.confidence)}` +
    (routed ? "." : ", a straight-line estimate and not a measured route.");
  return (
    <View style={styles.transfer} accessible accessibilityLabel={label}>
      <View style={styles.timeCol} />
      <View style={[styles.connector, !routed && styles.connectorDashed]} />
      <Text style={styles.transferText}>{text}</Text>
      <Tag routed={routed} />
    </View>
  );
}

/** A day's stops in time order. Plain views: a day has at most 40 stops. */
export function DayPlanList({
  day,
  previousDay,
  showBase,
  selectedId,
  onSelect,
  onDetails,
  actions,
  onRowLayout,
}: {
  day: Day;
  previousDay?: Day;
  showBase: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDetails?: (item: Item) => void;
  actions?: ItemActions;
  /** Where each row sits, so a screen can scroll to the stop chosen on the map. */
  onRowLayout?: (id: string, y: number) => void;
}) {
  const rows = useMemo(() => buildDayRows(day), [day]);
  const transport = transportPoint(day, previousDay);
  return (
    <View style={styles.list}>
      <DayHead day={day} showBase={showBase} />
      {day.arrival ? (
        <View onLayout={(e) => onRowLayout?.(`arrival-${day.id}`, e.nativeEvent.layout.y)}>
          <ArrivalRow
            day={day}
            selectable={transport !== null}
            selected={transport !== null && selectedId === transport.id}
            onSelect={() => transport && onSelect(transport.id)}
          />
        </View>
      ) : null}
      {rows.length === 0 ? <Text style={styles.empty}>Nothing is planned on this day.</Text> : null}
      {rows.map((row) =>
        row.kind === "item" ? (
          <View key={row.key} onLayout={(e) => onRowLayout?.(row.key, e.nativeEvent.layout.y)}>
            <StopRow
              item={row.item}
              ordinal={row.ordinal}
              selected={selectedId === row.item.id}
              onSelect={() => onSelect(row.item.id)}
              onDetails={onDetails ? () => onDetails(row.item) : undefined}
              actions={actions}
            />
          </View>
        ) : (
          <TransferRow key={row.key} row={row} />
        ),
      )}
    </View>
  );
}

// ---- the whole view ----------------------------------------------------------------------------

export type PlanMode = "list" | "map";

/**
 * A plan, one day at a time. In list mode the stops fill the space (or flow inside a parent's
 * scroll view with `embedded`); in map mode the map sits above the list and both share the
 * selection: a marker scrolls the list to its stop, a stop moves the map to its marker.
 */
export function PlanDayView({
  days,
  dayIndex,
  onDayChange,
  mode,
  map,
  initialSelectedId = null,
  onDetails,
  actions,
  onShowList,
  header,
  embedded = false,
}: {
  days: Day[];
  dayIndex: number;
  onDayChange: (dayIndex: number) => void;
  mode: PlanMode;
  /** The map style from the server; null without a connection. */
  map: ClientConfig["map"] | null;
  initialSelectedId?: string | null;
  onDetails?: (item: Item) => void;
  actions?: ItemActions;
  onShowList: () => void;
  /** Shown above the list in list mode (notices, plan notes). */
  header?: ReactNode;
  embedded?: boolean;
}) {
  const sorted = useMemo(() => [...days].sort((a, b) => a.day_index - b.day_index), [days]);
  const position = Math.max(
    0,
    sorted.findIndex((d) => d.day_index === dayIndex),
  );
  const day = sorted[position];
  const previousDay = position > 0 ? sorted[position - 1] : undefined;
  const showBase = useMemo(
    () => new Set(sorted.map((d) => d.base_city_name ?? "")).size > 1,
    [sorted],
  );
  // The selection belongs to one day; another day starts with nothing selected.
  const [selection, setSelection] = useState<{ dayId: string; id: string } | null>(() => {
    if (!initialSelectedId || !day) return null;
    return { dayId: day.id, id: initialSelectedId };
  });
  const selectedId = selection && day && selection.dayId === day.id ? selection.id : null;

  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);
  const rowY = useRef(new Map<string, number>());
  const fromMap = useRef(false);
  useEffect(() => {
    if (!selectedId || !fromMap.current) return;
    fromMap.current = false;
    const y = rowY.current.get(selectedId);
    if (y !== undefined) scroller.current?.scrollTo({ y: Math.max(0, y - spacing.sm) });
  }, [selectedId]);

  if (!day) {
    return <EmptyState title="No days" text="This plan has no days." />;
  }

  const select = (id: string) => setSelection({ dayId: day.id, id });
  const list = (
    <DayPlanList
      day={day}
      previousDay={previousDay}
      showBase={showBase}
      selectedId={selectedId}
      onSelect={select}
      onDetails={onDetails}
      actions={actions}
      onRowLayout={(id, y) => rowY.current.set(id, y)}
    />
  );
  const strip = <DayStrip days={sorted} value={day.day_index} onChange={onDayChange} />;

  if (mode === "list") {
    if (embedded) {
      return (
        <View style={styles.embedded}>
          {strip}
          {list}
        </View>
      );
    }
    return (
      <ScrollView ref={scroller} contentContainerStyle={styles.scrollContent}>
        {header}
        {strip}
        {list}
      </ScrollView>
    );
  }

  return (
    <View style={styles.fill}>
      {strip}
      <View style={styles.mapArea}>
        {map ? (
          <ItineraryMap
            day={day}
            previousDay={previousDay}
            map={map}
            onShowList={onShowList}
            selectedId={selectedId}
            onSelect={(id) => {
              fromMap.current = true;
              select(id);
            }}
          />
        ) : (
          <EmptyState
            title="The map needs a connection"
            text="The map style comes from the server, and the map tiles come from the internet. The day list works offline."
            action={{ label: "Show the day list", onPress: onShowList }}
          />
        )}
      </View>
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <ScrollView ref={scroller} contentContainerStyle={styles.sheetContent}>
          {list}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  embedded: { gap: spacing.sm, marginHorizontal: -spacing.lg },
  scrollContent: { paddingBottom: spacing.xxl },
  mapArea: { flex: 1.1, minHeight: 220 },
  sheet: {
    flex: 1,
    marginTop: -radius.lg,
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    ...shadow.raised,
  },
  sheetContent: { paddingBottom: spacing.xl },
  grabber: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    marginTop: spacing.sm,
    backgroundColor: colors.border,
  },

  strip: { flexGrow: 0 },
  stripContent: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.sm },
  dayPill: {
    minHeight: TOUCH + 4,
    minWidth: 72,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  dayPillActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayPillTitle: { ...type.small, fontWeight: "700", color: colors.text },
  dayPillDate: { ...type.caption, color: colors.muted },
  dayPillTextActive: { color: colors.onPrimary },

  list: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  dayHead: { paddingTop: spacing.md, paddingBottom: spacing.xs, gap: spacing.xxs },
  dayHeadTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  dayHeadTitle: { ...type.title, color: colors.text },
  basePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
  },
  basePillText: { ...type.caption, fontWeight: "600", color: colors.primary },
  empty: { ...type.small, color: colors.muted, paddingVertical: spacing.md },

  row: { flexDirection: "row", gap: spacing.md },
  timeCol: { width: 44, paddingTop: spacing.md },
  time: { ...type.small, fontWeight: "700", color: colors.text },
  timeEnd: { ...type.caption, color: colors.muted },
  card: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.card,
  },
  cardRow: { flexDirection: "row", alignItems: "center" },
  cardEat: { borderLeftWidth: 4, borderLeftColor: colors.eat },
  // Selected: a thick teal border, and the state is announced.
  cardSelected: { borderColor: colors.primary, borderWidth: 2 },
  select: {
    flex: 1,
    minHeight: TOUCH + 16,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
  },
  chevron: { width: TOUCH, minHeight: TOUCH, alignItems: "center", justifyContent: "center" },
  disc: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.marker,
    alignItems: "center",
    justifyContent: "center",
  },
  discEat: { backgroundColor: colors.eat, borderRadius: radius.sm },
  discTransport: { backgroundColor: colors.ink, borderRadius: radius.sm, margin: spacing.md },
  discQuiet: { backgroundColor: colors.surfaceMuted },
  discText: { color: colors.onPrimary, fontWeight: "700", fontSize: 14 },
  cardText: { flex: 1, gap: spacing.xxs, paddingVertical: spacing.sm },
  title: { ...type.body, fontWeight: "700", color: colors.text },
  kind: { ...type.small, fontWeight: "600" },
  kindSight: { color: colors.primary },
  kindEat: { color: colors.accentText },
  meta: { ...type.small, color: colors.muted },
  tags: { ...type.caption, fontWeight: "700", color: colors.primary },
  expanded: {
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: spacing.sm,
  },
  reason: { ...type.small, color: colors.text },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },

  transfer: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 28 },
  connector: {
    width: 0,
    height: 22,
    borderLeftWidth: 2,
    borderColor: colors.outline,
    marginLeft: spacing.lg,
  },
  connectorDashed: { borderStyle: "dashed" },
  transferText: { ...type.caption, color: colors.muted },
  tag: {
    ...type.caption,
    fontWeight: "700",
    color: colors.text,
    paddingHorizontal: spacing.sm,
    paddingVertical: 1,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderColor: colors.outline,
    overflow: "hidden",
    alignSelf: "flex-start",
  },
  tagRouted: { borderStyle: "solid" },
  tagEstimated: { borderStyle: "dashed" },
});
