import type { Itinerary, Item, Trip } from "@detour/shared";
import { useCallback, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { IconButton, Tabs } from "../components/ds/primitives";
import { PlanDayView } from "../components/plan/DayPlan";
import { ResourceNotices } from "../components/ResourceNotices";
import {
  CompactHeader,
  ErrorState,
  LoadingState,
  Notice,
  PlanNotes,
  WakingServer,
} from "../components/ui";
import { keys, useTripActions } from "../data/actions";
import { useItemActions } from "../data/itemActions";
import { useResource } from "../data/DataProvider";
import { PROFILE_LABEL, planNames } from "../domain/compare";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { pluralise } from "../util/format";

export { arrivalText, dayTitle, dayTotalsText } from "../components/plan/DayPlan";

type ItineraryRoute = Extract<Route, { name: "itinerary" }>;

/** The plan's own numbers, said once: how many transfers are estimated. */
export function estimatedNoteOf(plan: Itinerary): string | null {
  const stats = plan.stats;
  return stats && stats.estimated_transfers > 0
    ? `${pluralise(stats.estimated_transfers, "transfer")} of ${stats.routed_transfers + stats.estimated_transfers} ${stats.estimated_transfers === 1 ? "is" : "are"} estimated: straight-line distance with a detour factor, not a measured route. Estimates are labelled.`
    : null;
}

/** Plan notes worth their own control: the rest are said elsewhere. */
export function listedNotes(plan: Itinerary) {
  return plan.notes.filter(
    (n) =>
      !n.code.startsWith("PROFILE_") &&
      n.code !== "ESTIMATED_TRANSFERS" &&
      n.code !== "DISTINCT_PLANS",
  );
}

/**
 * One plan, a day at a time, as a list or as a map with the list under it (ADR 021, step 3).
 * Reached from the proposals (any plan) and from a trip's overview (its active itinerary).
 */
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
  const items = useItemActions(route.tripId, route.itineraryId);
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
  if (data === undefined) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Plan" onBack={nav.back} />
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
  // Planned itineraries of an active trip can be changed; a plan made by hand cannot be recalculated.
  const editable = trip?.status !== "past" && items.connected;
  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;
  const estimatedNote = estimatedNoteOf(data);
  const error = problem ?? items.problem;

  const openDetails = (item: Item) =>
    nav.push({
      name: "placeDetail",
      tripId: route.tripId,
      itineraryId: route.itineraryId,
      itemId: item.id,
    });

  const top = (
    <View>
      <CompactHeader
        title={trip ? planNames(data, trip.destination.name).title : `${label} plan`}
        subtitle={trip ? `${label} plan · ${trip.title}` : undefined}
        onBack={nav.back}
        right={
          <IconButton
            icon="settings"
            label="Trip settings"
            hint="Ask for new proposals or delete the trip"
            compact
            testID="trip-settings"
            onPress={() => nav.push({ name: "tripSettings", tripId: route.tripId })}
          />
        }
      />
      <ResourceNotices resource={itinerary} noun="this plan" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Tabs<"days" | "map">
        items={[
          { key: "map", label: "Map", accessibilityLabel: "Show the map" },
          { key: "days", label: "List", accessibilityLabel: "Show the day list" },
        ]}
        value={route.view}
        onChange={(v) => setView(v)}
        compact
        testID="show"
      />
      {editable ? (
        <View style={styles.toolbar}>
          <Button
            label="Add a place"
            icon="sight"
            variant="secondary"
            size="compact"
            testID="add-place"
            hint="Search or drop a pin; you see what would change first"
            onPress={() =>
              nav.push({ name: "addPlace", tripId: route.tripId, itineraryId: route.itineraryId })
            }
          />
          <Button
            label="Add a restaurant"
            icon="restaurant"
            variant="secondary"
            size="compact"
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
        </View>
      ) : null}
    </View>
  );

  const notes = (
    <View>
      {estimatedNote ? (
        <Notice tone="info" label="About travel times">
          {estimatedNote}
        </Notice>
      ) : null}
      <PlanNotes notes={listedNotes(data)} />
    </View>
  );

  return (
    <View style={styles.fill}>
      {route.view === "map" ? top : null}
      <PlanDayView
        // A new day from outside (another route) resets the shared selection.
        key={`${route.view}`}
        days={data.days}
        dayIndex={route.day}
        onDayChange={(d) => setView(route.view, d)}
        mode={route.view === "map" ? "map" : "list"}
        map={mapConfig}
        initialSelectedId={route.itemId ?? null}
        onDetails={openDetails}
        onShowList={() => setView("days")}
        header={
          <>
            {top}
            {notes}
          </>
        }
      />
      {/* The choice is always at hand, under the map and the stops (reference screen 14). */}
      <View style={styles.choose}>
        {selected ? (
          <Text style={styles.selectedBadge}>✓ Selected</Text>
        ) : (
          <Button
            label="Choose this itinerary"
            variant="ink"
            fill
            testID="choose-itinerary"
            accessibilityLabel={`Select the ${label} plan`}
            loading={selecting}
            onPress={() => void select()}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    flexWrap: "wrap",
  },
  choose: {
    padding: spacing.md,
    paddingHorizontal: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.background,
  },
  selectedBadge: {
    textAlign: "center",
    ...type.small,
    fontWeight: "700",
    color: colors.primary,
    backgroundColor: colors.primarySoft,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    overflow: "hidden",
  },
});
