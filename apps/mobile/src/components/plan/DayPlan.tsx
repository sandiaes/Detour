import type { ClientConfig, Day, Item } from "@detour/shared";
import { type ComponentRef, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

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
  formatDate,
  formatMeters,
  formatMinutes,
  formatSeconds,
  pluralise,
} from "../../util/format";
import { Icon } from "../ds/Icon";
import { KindIcon } from "../ds/KindIcon";
import { EmptyState } from "../ui";
import { ItineraryMap } from "../ItineraryMap";

// One day of a plan (ADR 021, step 3): a day selector, the day's stops in time order, and the map.
// The list and the map share one selection: choosing a stop in either highlights it in both.

export function dayTitle(day: Day): string {
  return day.date
    ? `Day ${day.day_index} · ${formatDate(day.date, false)}`
    : `Day ${day.day_index}`;
}

export function dayTotalsText(day: Day): string {
  const t = dayTotals(day);
  if (t.visits === 0 && t.meals === 0) return "Nothing planned";
  const meals = t.meals > 0 ? ` · ${pluralise(t.meals, "place to eat", "places to eat")}` : "";
  return `${pluralise(t.visits, "visit")}${meals} · ${formatMinutes(t.visitMinutes)} at the sights · ${formatSeconds(t.travelSeconds)} travelling`;
}

export const UNKNOWN_LEG_TEXT = "time not calculated: public transport is not built yet";

/** The drive from the previous base city that starts the day, as one line. */
export function arrivalText(day: Day): string | null {
  const a = day.arrival;
  if (!a) return null;
  const from = a.from_base_city_name ? ` from ${a.from_base_city_name}` : "";
  // A leg into or out of a country travelled by rail has no time (ADR 024): never a made-up one.
  if (a.mode === "unknown" || a.seconds === null || a.meters === null) {
    return `Travel${from} · ${UNKNOWN_LEG_TEXT}`;
  }
  return `${a.mode === "walk" ? "Walk" : "Drive"}${from} · ${formatSeconds(a.seconds)} · ${formatMeters(a.meters)}`;
}

/** "Restaurant · 1 h 15 min" or "Attraction · 2 h": what a stop is, in words, and how long. */
export function stopSummary(item: Item): string {
  const kind = stopKind(item);
  const parts: string[] = [];
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
        ? "typical length"
        : "typical visit length";
  const kind = item.type === "free_time" ? "Free time" : null;
  const when = start ? (end ? `${start} to ${end}` : start) : "Time not set";
  const reasons = item.reason_texts.join(" ");
  const tags = [item.locked ? "Locked" : null, item.origin === "user" ? "Added by you" : null]
    .filter(Boolean)
    .join(" · ");
  return (
    `${ordinal ? `Stop ${ordinal}. ` : ""}${item.type === "free_time" ? "" : `${STOP_KIND_LABEL[stopKind(item)]}. `}${kind ? `${kind}. ` : ""}${item.display_name}. ` +
    `${tags ? `${tags}. ` : ""}${when}. ` +
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
  // Pills share the width when there are few days and scroll sideways when there are many. The
  // text is centred in each pill, with or without a date.
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
            hitSlop={{ top: 2, bottom: 2 }}
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

/** No "Day 3 · Tue 1 Dec · 8 visits…" title: the strip above already names the day. Only a trip
 * that moves between base cities says where the day is based, in one quiet line. */
function DayHead({ day, showBase }: { day: Day; showBase: boolean }) {
  const base = showBase && day.base_city_name ? day.base_city_name : null;
  if (!base) return null;
  return (
    <Text style={styles.dayBaseLine} accessibilityLabel={`${dayTitle(day)}. Based in ${base}.`}>
      {base}
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
    <View style={[styles.row, selected && styles.rowSelected]}>
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
        style={[styles.body, styles.cardRow]}
        testID={`arrival-${day.day_index}`}
      >
        <View style={[styles.disc, styles.discTransport]}>
          <Icon name="transport" size={14} color={colors.onPrimary} />
        </View>
        <View style={styles.cardText}>
          <Text style={styles.title}>
            {day.base_city_name ? `To ${day.base_city_name}` : "Travel"}
          </Text>
          <Text style={styles.meta}>{text}</Text>
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
}: {
  item: Item;
  ordinal: number | null;
  selected: boolean;
  onSelect: () => void;
  onDetails?: () => void;
}) {
  const start = formatClock(item.start_time);
  const end = formatClock(item.end_time);
  const stop = stopKind(item);
  const eat = isEatKind(stop);
  const tags = [item.locked ? "Locked" : null, item.origin === "user" ? "Added by you" : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <View style={[styles.row, selected && styles.rowSelected]}>
      <View style={styles.timeCol}>
        <Text style={styles.time}>{start ?? "–"}</Text>
        {end ? <Text style={styles.timeEnd}>{end}</Text> : null}
      </View>
      <View style={styles.body}>
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
              // Sights are round and teal, places to eat rounded-square and orange, and the words
              // below say it too: never colour alone.
              <View style={[styles.disc, eat && styles.discEat]}>
                <Text style={styles.discText} maxFontSizeMultiplier={1.3}>
                  {ordinal}
                </Text>
              </View>
            ) : (
              <View style={[styles.disc, styles.discQuiet]}>
                <Icon name="clock" size={14} color={colors.muted} />
              </View>
            )}
            <View style={styles.cardText}>
              <Text style={styles.title}>{item.display_name}</Text>
              <View style={styles.kindLine}>
                <KindIcon kind={stop} size={13} />
                <Text
                  testID={`kind-${stop}`}
                  style={[styles.kind, eat ? styles.kindEat : styles.kindSight]}
                >
                  {stopSummary(item)}
                </Text>
              </View>
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
              <Icon name="chevronRight" size={16} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
      </View>
    </View>
  );
}

/** Travel between two stops, written into a hairline: ———— Walk · 3 min · 170 m ————. The words
 * for a screen reader still say when a time is only an estimate. */
/** An idle stretch between two stops, in a hairline like a transfer, with no place or icon. */
export function FreeTimeRow({ row }: { row: Extract<DayRow, { kind: "free" }> }) {
  const text = `Free time · ${formatMinutes(row.minutes)} · ${row.start} to ${row.end}`;
  return (
    <View
      style={styles.transfer}
      accessible
      accessibilityLabel={`Free time, ${formatMinutes(row.minutes)}, from ${row.start} to ${row.end}`}
      testID="free-time"
    >
      <View style={styles.transferLine} />
      <Text style={styles.transferText}>{text}</Text>
      <View style={styles.transferLine} />
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
      <View style={styles.transferLine} />
      <Text style={styles.transferText}>{text}</Text>
      <View style={styles.transferLine} />
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
  onRowLayout,
}: {
  day: Day;
  previousDay?: Day;
  showBase: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDetails?: (item: Item) => void;
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
            />
          </View>
        ) : row.kind === "free" ? (
          <FreeTimeRow key={row.key} row={row} />
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
  onSelectionChange,
  onDetails,
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
  /** Told when the user selects a stop, so a screen can keep it for when the user comes back. */
  onSelectionChange?: (id: string) => void;
  onDetails?: (item: Item) => void;
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

  const select = (id: string) => {
    setSelection({ dayId: day.id, id });
    onSelectionChange?.(id);
  };
  const list = (
    <DayPlanList
      day={day}
      previousDay={previousDay}
      showBase={showBase}
      selectedId={selectedId}
      onSelect={select}
      onDetails={onDetails}
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
        {strip}
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
  // The map is the smaller part: the stops beneath it are what is read and tapped.
  // Clipped, so a marker dragged past the map's edge never draws over the tabs or the stops.
  mapArea: { flex: 0.8, minHeight: 150, overflow: "hidden", zIndex: 0 },
  sheet: {
    flex: 1.5,
    zIndex: 1,
    marginTop: -radius.lg,
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    ...shadow.raised,
  },
  sheetContent: { paddingBottom: spacing.xl },

  // Never shrinks or clips: its height is its pills' height plus the padding.
  strip: { flexGrow: 0, flexShrink: 0 },
  stripContent: {
    flexGrow: 1,
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  // Compact pills with the stops' own type: day in small semibold, date in caption.
  dayPill: {
    flex: 1,
    minWidth: 84,
    height: 44,
    paddingHorizontal: spacing.md,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
  },
  dayPillActive: { backgroundColor: colors.ink },
  dayPillTitle: { ...type.small, fontWeight: "600", color: colors.text, textAlign: "center" },
  dayPillDate: { ...type.caption, lineHeight: 16, color: colors.muted, textAlign: "center" },
  dayPillTextActive: { color: colors.onPrimary },

  // The list sits 8 dp from the screen edge and every row pads its content by 12 dp, so text is
  // 20 dp in and a selected row's soft rounded tint has the same room all around it.
  list: { paddingHorizontal: spacing.sm },
  dayBaseLine: {
    ...type.caption,
    color: colors.muted,
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  empty: {
    ...type.small,
    color: colors.muted,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },

  // A stop is a flat row. Selected: a light tint, announced as selected.
  // No hairline of its own: the travel line between two stops is the divider.
  row: {
    flexDirection: "row",
    gap: spacing.md,
    paddingLeft: spacing.md,
    borderRadius: radius.md,
  },
  rowSelected: { backgroundColor: colors.surfaceMuted },
  timeCol: { width: 40, paddingTop: spacing.md },
  time: { ...type.caption, fontWeight: "700", color: colors.text },
  timeEnd: { ...type.caption, color: colors.muted },
  body: { flex: 1 },
  cardRow: { flexDirection: "row", alignItems: "center" },
  select: {
    flex: 1,
    minHeight: TOUCH + 8,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  chevron: { width: 40, minHeight: TOUCH, alignItems: "center", justifyContent: "center" },
  disc: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.marker,
    alignItems: "center",
    justifyContent: "center",
  },
  discEat: { backgroundColor: colors.eat, borderRadius: 7 },
  discTransport: { backgroundColor: colors.ink, borderRadius: 7 },
  discQuiet: { backgroundColor: colors.surfaceMuted },
  discText: { color: colors.onPrimary, fontWeight: "600", fontSize: 12 },
  cardText: { flex: 1, gap: 1 },
  title: { ...type.small, fontWeight: "600", color: colors.text },
  kindLine: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  kind: { ...type.caption, fontWeight: "500" },
  kindSight: { color: colors.primary },
  kindEat: { color: colors.accentText },
  meta: { ...type.caption, color: colors.muted },
  tags: { ...type.caption, fontWeight: "700", color: colors.primary },

  transfer: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 28,
    paddingHorizontal: spacing.md,
  },
  transferLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  transferText: { ...type.caption, color: colors.muted },
});
