import type { ItinerarySummary, Trip } from "@detour/shared";
import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import {
  Badge,
  Bullets,
  Button,
  Card,
  CompactHeader,
  EmptyState,
  ErrorState,
  Icon,
  IconButton,
  InlineStatus,
  ListRow,
  LoadingState,
  MetaLine,
  Notice,
  SectionHeader,
  StateView,
  WakingServer,
} from "../components/ds";
import { Cover } from "../components/ds/Cover";
import { PlanNotes } from "../components/plan/PlanNotes";
import { ResourceNotices } from "../components/ResourceNotices";
import { keys, useTripActions } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useLocalCover } from "../documents/DocumentsProvider";
import { PROFILE_EMPHASIS, PROFILE_LABEL, buildComparison, planNames } from "../domain/compare";
import { useNavigation } from "../nav/Navigator";
import { PastTripScreen } from "./PastTripScreen";
import { border, colors, layout, radius, spacing, type, weight } from "../theme";
import { formatSeconds, formatTripSpan, pluralise } from "../util/format";

/** Notes that need no space of their own: the profile is described on its card, the overlap in the
 * comparison, and a single plan's reason is shown on the card. */
export function isGeneralNote(n: { code: string }): boolean {
  return !n.code.startsWith("PROFILE_") && n.code !== "DISTINCT_PLANS" && n.code !== "SINGLE_PLAN";
}

/** A multi-city trip's plan made before its cities changed cannot be chosen (ADR 024). */
export function madeForEarlierStops(plan: ItinerarySummary, trip: Trip): boolean {
  return (
    trip.destination.kind === "route" && (plan.stops_version ?? 0) !== (trip.stops_version ?? 0)
  );
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

/** The comparison, flat: hairline rows, no card. Opened from the "Compare itineraries" row. */
function ComparisonTable({ a, b }: { a: ItinerarySummary; b: ItinerarySummary }) {
  const { rows, differences } = buildComparison(a, b);
  const nameA = PROFILE_LABEL[a.profile];
  const nameB = PROFILE_LABEL[b.profile];
  return (
    <View style={styles.compare}>
      <SectionHeader title="How they differ" />
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
      <Bullets items={differences} />
    </View>
  );
}

function PlanCard({
  plan,
  trip,
  busy,
  onView,
  onSelect,
}: {
  plan: ItinerarySummary;
  trip: Trip;
  busy: boolean;
  onView: () => void;
  onSelect: () => void;
}) {
  const label = PROFILE_LABEL[plan.profile];
  const selected = plan.status === "selected";
  const stale = madeForEarlierStops(plan, trip);
  const names = planNames(plan, trip.destination.name);
  const localCover = useLocalCover(trip.id);
  const s = plan.stats;
  return (
    <Card testID={`plan-${plan.profile}`}>
      <Cover
        seedKey={`${trip.destination.ref}:${plan.profile}`}
        photo={trip.cover_image}
        uri={localCover?.uri ?? null}
        height={140}
        rounded={radius.md}
      >
        {names.badge || selected ? (
          <View style={styles.planBadge}>
            <Badge label={selected ? "Selected" : (names.badge as string)} tone="primary" />
          </View>
        ) : null}
      </Cover>
      <View style={styles.planBody}>
        <View
          accessible
          accessibilityRole="header"
          accessibilityLabel={`${label} plan. ${names.title}`}
        >
          <Text style={styles.planTitle}>{names.title}</Text>
          <Text style={styles.planTagline}>{names.tagline}</Text>
        </View>
        <Text style={styles.body}>{PROFILE_EMPHASIS[plan.profile]}</Text>
        {s ? (
          <View style={styles.facts}>
            <MetaLine icon="sight" text={pluralise(s.visits, "place")} />
            {(s.meals ?? 0) > 0 ? (
              <MetaLine icon="restaurant" text={pluralise(s.meals ?? 0, "restaurant")} />
            ) : null}
            <MetaLine icon="route" text={`${formatSeconds(s.travel_seconds)} travelling`} />
          </View>
        ) : null}
        {plan.notes
          .filter((n) => n.code === "SINGLE_PLAN")
          .map((n) => (
            <Text key={n.code} style={styles.note}>
              {n.text}
            </Text>
          ))}
        {stale ? (
          <Text style={styles.note} testID={`stale-${plan.profile}`}>
            Made for the trip&apos;s earlier cities. Get new proposals in the trip settings.
          </Text>
        ) : null}
        <View style={styles.actions}>
          <View style={styles.flex}>
            <Button
              testID={`view-details-${plan.profile}`}
              label="View details"
              variant="secondary"
              size="sm"
              fill
              onPress={onView}
              accessibilityLabel={`View the details of the ${label} plan`}
            />
          </View>
          <View style={styles.flex}>
            <Button
              testID={`select-${plan.profile}`}
              label={selected ? "Selected" : "Choose this itinerary"}
              size="sm"
              fill
              accessibilityLabel={
                selected ? `The ${label} plan is selected` : `Select the ${label} plan`
              }
              disabled={selected || stale}
              loading={busy}
              onPress={onSelect}
            />
          </View>
        </View>
      </View>
    </Card>
  );
}

export function TripScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
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
  const [comparing, setComparing] = useState(false);

  const run = useCallback(async (id: string, work: () => Promise<void>) => {
    setBusy(id);
    setProblem(null);
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
      // The chosen plan is the trip's active itinerary from now on: open the trip's overview,
      // built around it, with the trips list under it (ADR 021).
      nav.resetTo([{ name: "trips" }, { name: "tripOverview", tripId }]);
    });

  const plan = () =>
    run("generate", async () => {
      await actions.generate(tripId);
    });

  // "View details": the plan's map with its days beneath (the list is one tap away there).
  const open = (p: ItinerarySummary) =>
    nav.push({ name: "itinerary", tripId, itineraryId: p.id, view: "map", day: 1 });

  if (trips.data === undefined) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Trip" onBack={nav.back} />
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
        <CompactHeader title="Trip" onBack={nav.back} />
        <EmptyState
          title="Trip not found"
          text="It may have been deleted."
          action={{ label: "Back to trips", onPress: () => nav.switchRoot({ name: "trips" }) }}
        />
      </View>
    );
  }

  // A trip that became past while this screen was open (or reached by a stale link).
  if (trip.status === "past") return <PastTripScreen tripId={tripId} />;

  const shown = plans.data ? visiblePlans(plans.data) : [];
  // After new proposals were asked for, the plan chosen earlier is kept apart from the new pair.
  const kept = shown.find(
    (p) =>
      p.status === "selected" &&
      shown.some((q) => q !== p && q.status !== "selected" && q.generation_id !== p.generation_id),
  );
  const proposals = shown.filter((p) => p !== kept);
  const pair = proposals.length >= 2 ? proposals.slice(0, 2) : null;

  const renderPlan = (p: ItinerarySummary) => (
    <PlanCard
      key={p.id}
      plan={p}
      trip={trip}
      busy={busy === p.id}
      onView={() => open(p)}
      onSelect={() => void select(p)}
    />
  );

  let content;
  if (plans.data === undefined) {
    content =
      plans.status === "error" ? (
        <ErrorState text={describeError(plans.error)} onRetry={plans.refresh} />
      ) : (
        <LoadingState text="Loading the plans…" />
      );
  } else if (shown.length === 0) {
    content = (
      <StateView
        kind="empty"
        layout="inline"
        icon="route"
        title="Not planned yet"
        text="Detour will propose two different plans to compare: one of the best-known sights, one that covers more."
      >
        <Button label="Plan this trip" loading={busy === "generate"} onPress={() => void plan()} />
        {busy === "generate" ? (
          <InlineStatus text="Planning… this usually takes a few seconds." />
        ) : null}
      </StateView>
    );
  } else {
    content = (
      <View style={styles.stack}>
        {kept ? (
          <View style={styles.pad}>
            <Notice tone="info" label="Your current plan is kept">
              It stays selected, with the places you added, until you choose one of the new
              proposals below.
            </Notice>
            {renderPlan(kept)}
          </View>
        ) : null}
        <View style={styles.pad}>
          <View style={styles.stack}>{proposals.map((p) => renderPlan(p))}</View>
        </View>
        {pair ? (
          <View style={styles.pad}>
            <ListRow
              icon="list"
              title="Compare itineraries"
              detail="See how the two plans differ"
              inset="none"
              accessibilityLabel="Compare itineraries"
              accessibilityHint="Shows how the two plans differ"
              expanded={comparing}
              trailing={<Icon name={comparing ? "up" : "down"} size="sm" color={colors.muted} />}
              onPress={() => setComparing((v) => !v)}
              testID="compare-toggle"
            />
            {comparing ? (
              <ComparisonTable a={pair[0] as ItinerarySummary} b={pair[1] as ItinerarySummary} />
            ) : null}
          </View>
        ) : null}
        <View style={styles.adjustLine}>
          <Icon name="info" size="sm" color={colors.muted} />
          <Text style={styles.note}>You can always adjust your itinerary later.</Text>
        </View>
      </View>
    );
  }

  const days = trip.duration_days;
  const subtitle = pair
    ? `We've created two options for your ${pluralise(days, "day")} trip to ${trip.destination.name}. Pick the one that fits your style, or look at both.`
    : `${trip.destination.name}`;
  const span = formatTripSpan(trip.start_date, trip.end_date, trip.duration_days);

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <CompactHeader
          title={trip.selected_itinerary_id ? "Original proposals" : "Choose your itinerary"}
          onBack={nav.back}
          right={
            <IconButton
              icon="settings"
              label="Trip settings"
              size="sm"
              testID="trip-settings"
              onPress={() => nav.push({ name: "tripSettings", tripId })}
            />
          }
        />
        <Text style={styles.intro}>{subtitle}</Text>
        <View style={styles.spanLine}>
          <Icon name="calendar" size="sm" color={colors.muted} />
          <Text style={styles.spanText}>{span}</Text>
        </View>
        <ResourceNotices resource={trips} noun="trips" inset />
        {problem ? (
          <Notice inset tone="error">
            {problem}
          </Notice>
        ) : null}
        {plans.data !== undefined ? <ResourceNotices resource={plans} noun="plans" inset /> : null}
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
  stack: { gap: layout.section },
  pad: { paddingHorizontal: layout.gutter, gap: layout.block },
  intro: {
    ...type.label,
    color: colors.muted,
    paddingHorizontal: layout.gutter,
    paddingBottom: spacing.sm,
  },
  spanLine: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: layout.gutter,
    paddingBottom: layout.block,
  },
  spanText: { ...type.label, fontWeight: weight.semibold, color: colors.text },
  planBadge: { position: "absolute", top: spacing.sm, left: spacing.sm },
  planBody: { gap: spacing.sm, paddingTop: spacing.xs },
  planTitle: { ...type.cardTitle, color: colors.text },
  planTagline: { ...type.caption, color: colors.muted },
  body: { ...type.label, color: colors.text },
  facts: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.lg, rowGap: spacing.xs },
  note: { ...type.caption, color: colors.muted },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  compare: { gap: spacing.xs, paddingTop: layout.block },
  adjustLine: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
  },
  tableHead: { flexDirection: "row", gap: spacing.sm },
  tableRow: {
    flexDirection: "row",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: border.hairline,
    borderTopColor: colors.border,
  },
  cellLabel: { flex: 1.1, ...type.label, color: colors.muted },
  cell: { flex: 1, ...type.label, color: colors.text },
  headText: { fontWeight: weight.bold, color: colors.text },
});
