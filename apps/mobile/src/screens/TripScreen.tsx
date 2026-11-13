import type { ItinerarySummary, Trip } from "@detour/shared";
import { useCallback, useRef, useState } from "react";
import {
  FlatList,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { ResourceNotices } from "../components/ResourceNotices";
import {
  Card,
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
import { PROFILE_EMPHASIS, PROFILE_LABEL, buildComparison, planFacts } from "../domain/compare";
import { useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { formatTripSpan } from "../util/format";

/** Wide enough to put the two plans next to each other instead of swiping. */
export const SIDE_BY_SIDE_MIN_WIDTH = 720;

/** Notes that need no space of their own: the profile is described on its card, the overlap in the
 * comparison, and a single plan's reason is shown on the card. */
export function isGeneralNote(n: { code: string }): boolean {
  return !n.code.startsWith("PROFILE_") && n.code !== "DISTINCT_PLANS" && n.code !== "SINGLE_PLAN";
}

/** The proposals of the latest generation, plus the selected plan if it is older. */
export function visiblePlans(all: ItinerarySummary[]): ItinerarySummary[] {
  const live = all.filter((p) => p.status !== "superseded");
  const engine = live.filter((p) => p.profile !== "manual");
  if (engine.length === 0) return live;
  const newest = [...engine].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const latest = engine.filter((p) => p.generation_id === newest?.generation_id);
  const selected = engine.find((p) => p.status === "selected");
  const shown = selected && !latest.includes(selected) ? [selected, ...latest] : latest;
  // Essentials first, then Wider, then anything else: a stable order for the comparison.
  const order = { essentials: 0, wider: 1, manual: 2 } as const;
  return shown.sort((a, b) => order[a.profile] - order[b.profile]);
}

function ComparisonTable({ a, b }: { a: ItinerarySummary; b: ItinerarySummary }) {
  const { rows, differences } = buildComparison(a, b);
  const nameA = PROFILE_LABEL[a.profile];
  const nameB = PROFILE_LABEL[b.profile];
  return (
    <Card>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        How they differ
      </Text>
      <View
        style={styles.tableHead}
        accessible={false}
        importantForAccessibility="no-hide-descendants"
      >
        <Text style={[styles.cellLabel, styles.headText]}> </Text>
        <Text style={[styles.cell, styles.headText]}>{nameA}</Text>
        <Text style={[styles.cell, styles.headText]}>{nameB}</Text>
      </View>
      {rows.map((row) => (
        <View
          key={row.key}
          style={styles.tableRow}
          accessible
          accessibilityLabel={`${row.label}: ${nameA} ${row.a}. ${nameB} ${row.b}.`}
        >
          <Text style={styles.cellLabel}>{row.label}</Text>
          <Text style={styles.cell}>{row.a}</Text>
          <Text style={styles.cell}>{row.b}</Text>
        </View>
      ))}
      {differences.map((text) => (
        <Text key={text} style={styles.difference}>
          • {text}
        </Text>
      ))}
    </Card>
  );
}

function PlanCard({
  plan,
  width,
  busy,
  onView,
  onMap,
  onSelect,
}: {
  plan: ItinerarySummary;
  width?: number;
  busy: boolean;
  onView: () => void;
  onMap: () => void;
  onSelect: () => void;
}) {
  const label = PROFILE_LABEL[plan.profile];
  const selected = plan.status === "selected";
  return (
    <View style={width ? { width } : styles.flex}>
      <Card accent={selected}>
        <View style={styles.planHead}>
          <Text accessibilityRole="header" style={styles.planTitle}>
            {label}
          </Text>
          {selected ? <Text style={styles.badge}>✓ Selected</Text> : null}
        </View>
        <Text style={styles.body}>{PROFILE_EMPHASIS[plan.profile]}</Text>
        {planFacts(plan).map((fact) => (
          <Text key={fact} style={styles.fact}>
            • {fact}
          </Text>
        ))}
        {plan.notes
          .filter((n) => n.code === "SINGLE_PLAN")
          .map((n) => (
            <Text key={n.code} style={styles.note}>
              {n.text}
            </Text>
          ))}
        <View style={styles.actions}>
          <Button
            testID={`view-days-${plan.profile}`}
            label="View days"
            variant="secondary"
            onPress={onView}
            accessibilityLabel={`View the days of the ${label} plan`}
          />
          <Button
            testID={`view-map-${plan.profile}`}
            label="View map"
            variant="secondary"
            onPress={onMap}
            accessibilityLabel={`View the ${label} plan on the map`}
          />
          <Button
            testID={`select-${plan.profile}`}
            label={selected ? "Selected" : "Select this plan"}
            accessibilityLabel={
              selected ? `The ${label} plan is selected` : `Select the ${label} plan`
            }
            disabled={selected}
            loading={busy}
            onPress={onSelect}
          />
        </View>
      </Card>
    </View>
  );
}

export function TripScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const { width } = useWindowDimensions();
  const actions = useTripActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const plans = useResource<ItinerarySummary[]>(
    keys.itineraries(tripId),
    (c) =>
      call(c.GET("/v1/trips/{trip_id}/itineraries", { params: { path: { trip_id: tripId } } })),
    { ttlMs: 10 * 60_000 },
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [announce, setAnnounce] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pager = useRef<FlatList<ItinerarySummary>>(null);

  const run = useCallback(async (id: string, work: () => Promise<void>) => {
    setBusy(id);
    setProblem(null);
    setAnnounce(null);
    try {
      await work();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(null);
    }
  }, []);

  const select = (plan: ItinerarySummary) =>
    run(plan.id, async () => {
      await actions.selectPlan(tripId, plan.id);
      setAnnounce(
        `The ${PROFILE_LABEL[plan.profile]} plan is now the selected plan for this trip.`,
      );
    });

  const plan = () =>
    run("generate", async () => {
      await actions.generate(tripId);
    });

  const open = (p: ItinerarySummary, view: "days" | "map") =>
    nav.push({ name: "itinerary", tripId, itineraryId: p.id, view, day: 1 });

  if (trips.data === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Trip" onBack={nav.back} />
        {trips.status === "error" ? (
          <ErrorState text={describeError(trips.error)} onRetry={trips.refresh} />
        ) : trips.waking ? (
          <WakingServer />
        ) : (
          <LoadingState text="Loading the trip…" />
        )}
      </View>
    );
  }
  if (!trip) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Trip" onBack={nav.back} />
        <EmptyState
          title="Trip not found"
          text="It may have been deleted."
          action={{ label: "Back to trips", onPress: () => nav.switchRoot({ name: "trips" }) }}
        />
      </View>
    );
  }

  const shown = plans.data ? visiblePlans(plans.data) : [];
  const pair = shown.length >= 2 ? shown.slice(0, 2) : null;
  const sideBySide = width >= SIDE_BY_SIDE_MIN_WIDTH;
  const pageWidth = Math.max(240, width - spacing.lg * 2);

  const onScrollEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    setPage(Math.round(e.nativeEvent.contentOffset.x / (pageWidth + spacing.md)));
  };

  const renderPlan = (p: ItinerarySummary, w?: number) => (
    <PlanCard
      key={p.id}
      plan={p}
      width={w}
      busy={busy === p.id}
      onView={() => open(p, "days")}
      onMap={() => open(p, "map")}
      onSelect={() => void select(p)}
    />
  );

  let content;
  if (trip.status === "past") {
    content = (
      <EmptyState
        title="A past trip"
        text="Its plans were archived when it ended. Viewing past trips on a map comes later."
      />
    );
  } else if (plans.data === undefined) {
    content =
      plans.status === "error" ? (
        <ErrorState text={describeError(plans.error)} onRetry={plans.refresh} />
      ) : (
        <LoadingState text="Loading the plans…" />
      );
  } else if (shown.length === 0) {
    content = (
      <View style={styles.pad}>
        <Card>
          <Text style={styles.planTitle}>Not planned yet</Text>
          <Text style={styles.body}>
            Detour will propose two different plans to compare: one of the best-known sights, one
            that covers more.
          </Text>
          <Button
            label="Plan this trip"
            loading={busy === "generate"}
            onPress={() => void plan()}
          />
          {busy === "generate" ? (
            <Text style={styles.note}>Planning… this usually takes a few seconds.</Text>
          ) : null}
        </Card>
      </View>
    );
  } else {
    content = (
      <View style={styles.stack}>
        {pair ? (
          <>
            <View style={styles.pad}>
              <ComparisonTable a={pair[0] as ItinerarySummary} b={pair[1] as ItinerarySummary} />
            </View>
            {sideBySide ? (
              <View style={[styles.pad, styles.row]}>{pair.map((p) => renderPlan(p))}</View>
            ) : (
              <>
                <View style={[styles.pad, styles.row]}>
                  {pair.map((p, i) => (
                    <Chip
                      key={p.id}
                      label={PROFILE_LABEL[p.profile]}
                      selected={page === i}
                      accessibilityLabel={`Show the ${PROFILE_LABEL[p.profile]} plan, ${i + 1} of 2`}
                      onPress={() => {
                        setPage(i);
                        pager.current?.scrollToIndex({ index: i, animated: true });
                      }}
                    />
                  ))}
                </View>
                <FlatList
                  ref={pager}
                  testID="plan-pager"
                  data={pair}
                  horizontal
                  pagingEnabled={false}
                  snapToInterval={pageWidth + spacing.md}
                  decelerationRate="fast"
                  showsHorizontalScrollIndicator={false}
                  keyExtractor={(p) => p.id}
                  renderItem={({ item }) => renderPlan(item, pageWidth)}
                  contentContainerStyle={styles.pagerContent}
                  ItemSeparatorComponent={() => <View style={{ width: spacing.md }} />}
                  onMomentumScrollEnd={onScrollEnd}
                  getItemLayout={(_, index) => ({
                    length: pageWidth + spacing.md,
                    offset: (pageWidth + spacing.md) * index,
                    index,
                  })}
                  accessibilityHint="Swipe sideways for the other plan"
                />
              </>
            )}
          </>
        ) : (
          <View style={styles.pad}>{shown.map((p) => renderPlan(p))}</View>
        )}
      </View>
    );
  }

  const subtitle = `${trip.destination.name} · ${formatTripSpan(trip.start_date, trip.end_date, trip.duration_days)}`;

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <ScreenHeader title={trip.title} subtitle={subtitle} onBack={nav.back} />
        <ResourceNotices resource={trips} noun="trips" />
        {announce ? (
          <Notice tone="info" label="Done">
            {announce}
          </Notice>
        ) : null}
        {problem ? <Notice tone="error">{problem}</Notice> : null}
        {plans.data !== undefined ? <ResourceNotices resource={plans} noun="plans" /> : null}
        {content}
        {shown[0] ? <PlanNotes notes={shown[0].notes.filter(isGeneralNote)} /> : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  flex: { flex: 1 },
  scroll: { paddingBottom: spacing.xxl },
  stack: { gap: spacing.md },
  pad: { paddingHorizontal: spacing.lg },
  row: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  pagerContent: { paddingHorizontal: spacing.lg },
  sectionTitle: { ...type.heading, color: colors.text },
  tableHead: { flexDirection: "row", gap: spacing.sm },
  tableRow: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  cellLabel: { flex: 1.1, ...type.small, color: colors.muted },
  cell: { flex: 1, ...type.small, color: colors.text },
  headText: { fontWeight: "700", color: colors.text },
  difference: { ...type.small, color: colors.text },
  planHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
  },
  planTitle: { ...type.title, color: colors.text, flexShrink: 1 },
  badge: {
    ...type.caption,
    fontWeight: "700",
    color: colors.primary,
    backgroundColor: colors.primarySoft,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
  body: { ...type.body, color: colors.text },
  fact: { ...type.small, color: colors.text },
  note: { ...type.small, color: colors.muted },
  actions: { gap: spacing.sm, marginTop: spacing.sm, alignItems: "stretch" },
});
