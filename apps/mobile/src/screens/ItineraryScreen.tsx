import type { Day, Itinerary, Item, Trip } from "@detour/shared";
import { useCallback, useMemo, useState } from "react";
import { ScrollView, SectionList, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError, planningIssues } from "../api/unwrap";
import { Button } from "../components/Button";
import { ItineraryMap } from "../components/ItineraryMap";
import { ResourceNotices } from "../components/ResourceNotices";
import {
  Chip,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  PlanNotes,
  ScreenHeader,
  WakingServer,
} from "../components/ui";
import { keys, useTripActions } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { PROFILE_LABEL } from "../domain/compare";
import {
  type DayRow,
  buildDayRows,
  STOP_KIND_LABEL,
  confidenceLabel,
  dayTotals,
  isEatKind,
  modeLabel,
  stopKind,
} from "../domain/itinerary";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import {
  formatClock,
  formatCuisines,
  formatDate,
  formatMeters,
  formatMinutes,
  formatSeconds,
  pluralise,
} from "../util/format";

type ItineraryRoute = Extract<Route, { name: "itinerary" }>;

const MEAL_LABEL = {
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

function DayHeader({ day, showBase }: { day: Day; showBase: boolean }) {
  const base = showBase && day.base_city_name ? `Based in ${day.base_city_name}` : null;
  const arrival = arrivalText(day);
  const routed = day.arrival?.confidence === "routed";
  const spoken =
    `${dayTitle(day)}. ${base ? `${base}. ` : ""}${dayTotalsText(day)}.` +
    (arrival
      ? ` Starts with: ${arrival}, ${routed ? "routed" : "estimated, a straight-line estimate and not a measured route"}.`
      : "");
  return (
    <View
      style={styles.dayHeader}
      accessible
      accessibilityRole="header"
      accessibilityLabel={spoken}
    >
      <Text style={styles.dayTitle}>{dayTitle(day)}</Text>
      {base ? <Text style={styles.dayBase}>{base}</Text> : null}
      <Text style={styles.dayMeta}>{dayTotalsText(day)}</Text>
      {arrival ? (
        <View style={styles.arrival}>
          <Text style={styles.transferText}>{arrival}</Text>
          <Text style={[styles.tag, routed ? styles.tagRouted : styles.tagEstimated]}>
            {routed ? "Routed" : "Estimated"}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

export type ItemActions = {
  onToggleLock: (item: Item) => void;
  onRemove: (item: Item) => void;
  /** The item whose lock or removal is being sent. */
  busyId: string | null;
};

export function ItemRow({
  item,
  ordinal,
  actions,
}: {
  item: Item;
  ordinal: number | null;
  actions?: ItemActions;
}) {
  const start = formatClock(item.start_time);
  const end = formatClock(item.end_time);
  const duration = formatMinutes(item.duration_minutes);
  const meal = item.type === "meal";
  const source =
    item.duration_source === "user"
      ? "set by you"
      : meal
        ? "typical meal length"
        : "typical visit length";
  const stop = stopKind(item);
  const eat = isEatKind(stop);
  const stopLabel = STOP_KIND_LABEL[stop];
  const kind =
    meal && item.meal_type
      ? MEAL_LABEL[item.meal_type]
      : item.type === "free_time"
        ? "Free time"
        : null;
  // Cuisine is what the open data says; there is no price or rating (ADR 016, ADR 017).
  const cuisine = meal ? formatCuisines(item.restaurant?.cuisines) : null;
  const when = start ? (end ? `${start} to ${end}` : start) : "Time not set";
  const reasons = item.reason_texts.join(" ");
  const tags = [item.locked ? "Locked" : null, item.origin === "user" ? "Added by you" : null]
    .filter(Boolean)
    .join(" · ");
  const label =
    `${ordinal ? `Stop ${ordinal}. ` : ""}${item.type === "free_time" ? "" : `${stopLabel}. `}${kind ? `${kind}. ` : ""}${item.display_name}. ` +
    `${tags ? `${tags}. ` : ""}${cuisine ? `${cuisine}. ` : ""}${when}. ` +
    `${duration}, ${source}.${reasons ? ` Why: ${reasons}` : ""}`;
  const busy = actions?.busyId === item.id;
  return (
    <View style={styles.itemRow}>
      <View style={styles.timeCol}>
        <Text style={styles.time}>{start ?? "–"}</Text>
        {end ? <Text style={styles.timeEnd}>{end}</Text> : null}
      </View>
      <View style={[styles.itemBody, eat && styles.itemBodyEat]}>
        <View accessible accessibilityLabel={label} style={styles.itemText}>
          <View style={styles.titleRow}>
            {ordinal ? (
              // Sights are round and green, places to eat are square and orange, and the tag
              // below says it in words: never colour alone.
              <View style={[styles.ordinal, eat && styles.ordinalEat]}>
                <Text style={styles.ordinalText} maxFontSizeMultiplier={1.3}>
                  {ordinal}
                </Text>
              </View>
            ) : null}
            <Text style={styles.itemTitle}>{item.display_name}</Text>
          </View>
          {item.type !== "free_time" ? (
            <Text
              testID={`kind-${stop}`}
              style={[styles.kindTag, eat ? styles.kindTagEat : styles.kindTagSight]}
            >
              {eat ? "🍴 " : ""}
              {stopLabel}
            </Text>
          ) : null}
          {kind ? <Text style={styles.itemMeta}>{kind}</Text> : null}
          {cuisine ? <Text style={styles.itemMeta}>{cuisine}</Text> : null}
          <Text style={styles.itemMeta}>
            {duration} · {source}
          </Text>
          {tags ? <Text style={styles.itemTags}>{tags}</Text> : null}
          {item.reason_texts.map((r) => (
            <Text key={r} style={styles.reason}>
              {r}
            </Text>
          ))}
        </View>
        {actions && item.type === "visit" ? (
          <View style={styles.itemActions}>
            <Button
              label={item.locked ? "Unlock" : "Lock"}
              variant="quiet"
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
              variant="quiet"
              disabled={busy || item.locked}
              accessibilityLabel={`Remove ${item.display_name}`}
              hint={item.locked ? "Unlock it first." : "Shows what would change first."}
              onPress={() => actions.onRemove(item)}
            />
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
    <View style={styles.transferRow} accessible accessibilityLabel={label}>
      <View style={styles.timeCol} />
      <View style={styles.transferBody}>
        <Text style={styles.transferText}>{text}</Text>
        {/* The label is a word, and the border differs (solid or dashed): not colour alone. */}
        <Text style={[styles.tag, routed ? styles.tagRouted : styles.tagEstimated]}>
          {routed ? "Routed" : "Estimated"}
        </Text>
      </View>
    </View>
  );
}

export function ItineraryScreen({ route }: { route: ItineraryRoute }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const actions = useTripActions();
  const changeActions = useChangeActions();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [issues, setIssues] = useState<string[]>([]);
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const itinerary = useResource<Itinerary>(
    keys.itinerary(route.itineraryId),
    (c) =>
      call(
        c.GET("/v1/itineraries/{itinerary_id}", {
          params: { path: { itinerary_id: route.itineraryId } },
        }),
      ),
    { ttlMs: 10 * 60_000 },
  );
  const [selecting, setSelecting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const trip = trips.data?.find((t) => t.id === route.tripId);

  const setView = (view: "days" | "map", day = route.day) => nav.replace({ ...route, view, day });

  const select = useCallback(async () => {
    setSelecting(true);
    setProblem(null);
    try {
      await actions.selectPlan(route.tripId, route.itineraryId);
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setSelecting(false);
    }
  }, [actions, route.tripId, route.itineraryId]);

  const toggleLock = useCallback(
    async (item: Item) => {
      setBusyId(item.id);
      setProblem(null);
      setIssues([]);
      try {
        await changeActions.setLocked(route.itineraryId, item.id, !item.locked);
      } catch (e) {
        setProblem(describeError(e));
      } finally {
        setBusyId(null);
      }
    },
    [changeActions, route.itineraryId],
  );

  const remove = useCallback(
    async (item: Item) => {
      setBusyId(item.id);
      setProblem(null);
      setIssues([]);
      try {
        const change = await changeActions.preview(route.itineraryId, {
          action: "remove_place",
          item_id: item.id,
        });
        nav.push({
          name: "changePreview",
          tripId: route.tripId,
          itineraryId: route.itineraryId,
          changeSetId: change.id,
        });
      } catch (e) {
        setProblem(describeError(e));
        setIssues(planningIssues(e));
      } finally {
        setBusyId(null);
      }
    },
    [changeActions, nav, route.itineraryId, route.tripId],
  );

  const data = itinerary.data;
  const sections = useMemo(
    () => (data ? data.days.map((d) => ({ day: d, data: buildDayRows(d) })) : []),
    [data],
  );
  // Base cities are worth naming only when the plan has more than one (an area trip).
  const showBase = useMemo(
    () => new Set((data?.days ?? []).map((d) => d.base_city_name ?? "")).size > 1,
    [data],
  );

  if (data === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Plan" onBack={nav.back} />
        {itinerary.status === "error" ? (
          <ErrorState
            title={itinerary.offline ? "You are offline" : "Something went wrong"}
            text={
              itinerary.offline
                ? "This plan is not saved on the device yet. Connect once to open it, and it will be available offline afterwards."
                : describeError(itinerary.error)
            }
            onRetry={itinerary.refresh}
          />
        ) : itinerary.waking ? (
          <WakingServer />
        ) : (
          <LoadingState text="Loading the plan…" />
        )}
      </View>
    );
  }

  const label = PROFILE_LABEL[data.profile];
  const selected = data.status === "selected";
  const stats = data.stats;
  const day = data.days.find((d) => d.day_index === route.day) ?? data.days[0];
  // Planned itineraries of an active trip can be changed; a plan made by hand cannot be recalculated.
  const editable = data.profile !== "manual" && trip?.status !== "past" && changeActions.connected;
  const itemActions: ItemActions | undefined = editable
    ? { onToggleLock: (i) => void toggleLock(i), onRemove: (i) => void remove(i), busyId }
    : undefined;

  const header = (
    <View>
      <ScreenHeader
        title={`${label} plan`}
        subtitle={trip ? `${trip.title} · ${trip.destination.name}` : undefined}
        onBack={nav.back}
        right={
          <Button
            testID="trip-settings"
            label="Trip settings"
            variant="quiet"
            hint="Ask for new proposals or delete the trip"
            onPress={() => nav.push({ name: "tripSettings", tripId: route.tripId })}
          />
        }
      />
      <ResourceNotices resource={itinerary} noun="this plan" />
      {problem ? <Notice tone="error">{[problem, ...issues].join(" ")}</Notice> : null}
      <View style={styles.toolbar}>
        <Chip
          label="Days"
          selected={route.view === "days"}
          onPress={() => setView("days")}
          accessibilityLabel="Show the day list"
        />
        <Chip
          label="Map"
          testID="show-map"
          selected={route.view === "map"}
          onPress={() => setView("map")}
          accessibilityLabel="Show the map"
        />
        <View style={styles.spacer} />
        {editable ? (
          <Button
            label="Add a place"
            variant="secondary"
            testID="add-place"
            hint="Search or drop a pin; you see what would change first"
            onPress={() =>
              nav.push({ name: "addPlace", tripId: route.tripId, itineraryId: route.itineraryId })
            }
          />
        ) : null}
        {editable ? (
          <Button
            label="Add a restaurant"
            variant="secondary"
            testID="add-restaurant"
            hint="Search or enter a restaurant; Detour suggests the best day and meal"
            onPress={() =>
              nav.push({
                name: "addRestaurant",
                tripId: route.tripId,
                itineraryId: route.itineraryId,
              })
            }
          />
        ) : null}
        {selected ? (
          <Text style={styles.selectedBadge}>✓ Selected</Text>
        ) : (
          <Button
            label="Select"
            accessibilityLabel={`Select the ${label} plan`}
            loading={selecting}
            onPress={() => void select()}
          />
        )}
      </View>
    </View>
  );

  if (route.view === "map") {
    const mapConfig = state.phase === "ready" ? state.connection.config.map : null;
    return (
      <View style={styles.fill}>
        {header}
        <ScrollView
          horizontal
          style={styles.dayStrip}
          contentContainerStyle={styles.dayStripContent}
          showsHorizontalScrollIndicator={false}
        >
          {data.days.map((d) => (
            <Chip
              key={d.id}
              label={`Day ${d.day_index}`}
              selected={day?.id === d.id}
              accessibilityLabel={`Show day ${d.day_index} on the map`}
              onPress={() => setView("map", d.day_index)}
            />
          ))}
        </ScrollView>
        {day && mapConfig ? (
          <ItineraryMap day={day} map={mapConfig} onShowList={() => setView("days")} />
        ) : (
          <EmptyState
            title="The map needs a connection"
            text="The map style comes from the server, and the map tiles come from the internet. The day list works offline."
            action={{ label: "Show the day list", onPress: () => setView("days") }}
          />
        )}
      </View>
    );
  }

  const estimatedNote =
    stats && stats.estimated_transfers > 0
      ? `${pluralise(stats.estimated_transfers, "transfer")} of ${stats.routed_transfers + stats.estimated_transfers} ${stats.estimated_transfers === 1 ? "is" : "are"} estimated: straight-line distance with a detour factor, not a measured route. Estimates are labelled.`
      : null;

  return (
    <SectionList
      sections={sections}
      keyExtractor={(row) => row.key}
      stickySectionHeadersEnabled
      ListHeaderComponent={
        <View>
          {header}
          {estimatedNote ? (
            <Notice tone="info" label="About travel times">
              {estimatedNote}
            </Notice>
          ) : null}
          <PlanNotes
            notes={data.notes.filter(
              (n) =>
                !n.code.startsWith("PROFILE_") &&
                n.code !== "ESTIMATED_TRANSFERS" &&
                n.code !== "DISTINCT_PLANS",
            )}
          />
        </View>
      }
      renderSectionHeader={({ section }) => <DayHeader day={section.day} showBase={showBase} />}
      renderItem={({ item: row }) =>
        row.kind === "item" ? (
          <ItemRow item={row.item} ordinal={row.ordinal} actions={itemActions} />
        ) : (
          <TransferRow row={row} />
        )
      }
      renderSectionFooter={({ section }) =>
        section.data.length === 0 ? (
          <Text style={styles.emptyDay}>Nothing is planned on this day.</Text>
        ) : null
      }
      initialNumToRender={12}
      maxToRenderPerBatch={12}
      windowSize={7}
      contentContainerStyle={styles.listContent}
      ListFooterComponent={<View style={{ height: spacing.xxl }} />}
    />
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  listContent: { paddingBottom: spacing.xl },
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    flexWrap: "wrap",
  },
  spacer: { flex: 1 },
  selectedBadge: {
    ...type.small,
    fontWeight: "700",
    color: colors.primary,
    backgroundColor: colors.primarySoft,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  dayStrip: { flexGrow: 0 },
  dayStripContent: { paddingHorizontal: spacing.lg, gap: spacing.sm, paddingBottom: spacing.md },
  dayHeader: {
    backgroundColor: colors.background,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  dayTitle: { ...type.title, color: colors.text },
  dayMeta: { ...type.small, color: colors.muted },
  dayBase: { ...type.small, fontWeight: "700", color: colors.text },
  arrival: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  emptyDay: { ...type.small, color: colors.muted, padding: spacing.lg },
  itemRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    gap: spacing.md,
  },
  timeCol: { width: 52 },
  time: { ...type.small, fontWeight: "700", color: colors.text },
  timeEnd: { ...type.caption, color: colors.muted },
  itemBody: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.xs,
  },
  itemBodyEat: { borderColor: colors.eat, borderLeftWidth: 5, backgroundColor: colors.eatSoft },
  kindTag: {
    ...type.caption,
    fontWeight: "700",
    alignSelf: "flex-start",
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    overflow: "hidden",
  },
  kindTagSight: {
    color: colors.marker,
    borderColor: colors.marker,
    backgroundColor: colors.primarySoft,
  },
  kindTagEat: { color: colors.eat, borderColor: colors.eat, backgroundColor: colors.surface },
  titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  itemText: { gap: spacing.xs },
  itemTags: { ...type.small, fontWeight: "700", color: colors.primary },
  itemActions: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  ordinal: {
    minWidth: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.marker,
    alignItems: "center",
    justifyContent: "center",
  },
  ordinalEat: { backgroundColor: colors.eat, borderRadius: radius.sm },
  ordinalText: { color: colors.onPrimary, fontWeight: "700", fontSize: 14 },
  itemTitle: { ...type.heading, color: colors.text, flexShrink: 1 },
  itemMeta: { ...type.small, color: colors.muted },
  reason: { ...type.small, color: colors.text },
  transferRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: spacing.md,
  },
  transferBody: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: spacing.sm,
    paddingLeft: spacing.md,
  },
  transferText: { ...type.small, color: colors.muted },
  tag: {
    ...type.caption,
    fontWeight: "700",
    color: colors.text,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderColor: colors.outline,
    overflow: "hidden",
  },
  tagRouted: { borderStyle: "solid" },
  tagEstimated: { borderStyle: "dashed" },
});
