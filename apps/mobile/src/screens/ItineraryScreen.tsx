import type { Day, Itinerary, Item, Trip } from "@detour/shared";
import { useCallback, useMemo, useState } from "react";
import { ScrollView, SectionList, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError } from "../api/unwrap";
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
import { useResource } from "../data/DataProvider";
import { PROFILE_LABEL } from "../domain/compare";
import {
  type DayRow,
  buildDayRows,
  confidenceLabel,
  dayTotals,
  modeLabel,
} from "../domain/itinerary";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import {
  formatClock,
  formatDate,
  formatMeters,
  formatMinutes,
  formatSeconds,
  pluralise,
} from "../util/format";

type ItineraryRoute = Extract<Route, { name: "itinerary" }>;

const MEAL_LABEL = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" } as const;

export function dayTitle(day: Day): string {
  return day.date
    ? `Day ${day.day_index} · ${formatDate(day.date, false)}`
    : `Day ${day.day_index}`;
}

function dayTotalsText(day: Day): string {
  const t = dayTotals(day);
  if (t.visits === 0) return "Nothing planned";
  return `${pluralise(t.visits, "visit")} · ${formatMinutes(t.visitMinutes)} at the sights · ${formatSeconds(t.travelSeconds)} travelling`;
}

export function ItemRow({ item, ordinal }: { item: Item; ordinal: number | null }) {
  const start = formatClock(item.start_time);
  const end = formatClock(item.end_time);
  const duration = formatMinutes(item.duration_minutes);
  const source = item.duration_source === "user" ? "set by you" : "typical visit length";
  const kind =
    item.type === "meal" && item.meal_type
      ? MEAL_LABEL[item.meal_type]
      : item.type === "free_time"
        ? "Free time"
        : null;
  const when = start ? (end ? `${start} to ${end}` : start) : "Time not set";
  const reasons = item.reason_texts.join(" ");
  const label =
    `${ordinal ? `Stop ${ordinal}. ` : ""}${kind ? `${kind}. ` : ""}${item.display_name}. ${when}. ` +
    `${duration}, ${source}.${reasons ? ` Why: ${reasons}` : ""}`;
  return (
    <View style={styles.itemRow} accessible accessibilityLabel={label}>
      <View style={styles.timeCol}>
        <Text style={styles.time}>{start ?? "–"}</Text>
        {end ? <Text style={styles.timeEnd}>{end}</Text> : null}
      </View>
      <View style={styles.itemBody}>
        <View style={styles.titleRow}>
          {ordinal ? (
            <View style={styles.ordinal}>
              <Text style={styles.ordinalText} maxFontSizeMultiplier={1.3}>
                {ordinal}
              </Text>
            </View>
          ) : null}
          <Text style={styles.itemTitle}>{item.display_name}</Text>
        </View>
        {kind ? <Text style={styles.itemMeta}>{kind}</Text> : null}
        <Text style={styles.itemMeta}>
          {duration} · {source}
        </Text>
        {item.reason_texts.map((r) => (
          <Text key={r} style={styles.reason}>
            {r}
          </Text>
        ))}
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

  const data = itinerary.data;
  const sections = useMemo(
    () => (data ? data.days.map((d) => ({ day: d, data: buildDayRows(d) })) : []),
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

  const header = (
    <View>
      <ScreenHeader
        title={`${label} plan`}
        subtitle={trip ? `${trip.title} · ${trip.destination.name}` : undefined}
        onBack={nav.back}
      />
      <ResourceNotices resource={itinerary} noun="this plan" />
      {problem ? <Notice tone="error">{problem}</Notice> : null}
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
      renderSectionHeader={({ section }) => (
        <View
          style={styles.dayHeader}
          accessible
          accessibilityRole="header"
          accessibilityLabel={`${dayTitle(section.day)}. ${dayTotalsText(section.day)}`}
        >
          <Text style={styles.dayTitle}>{dayTitle(section.day)}</Text>
          <Text style={styles.dayMeta}>{dayTotalsText(section.day)}</Text>
        </View>
      )}
      renderItem={({ item: row }) =>
        row.kind === "item" ? (
          <ItemRow item={row.item} ordinal={row.ordinal} />
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
  titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  ordinal: {
    minWidth: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.marker,
    alignItems: "center",
    justifyContent: "center",
  },
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
