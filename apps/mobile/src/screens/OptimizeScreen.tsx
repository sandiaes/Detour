import type { Itinerary, Trip } from "@detour/shared";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError, call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Card, EmptyState, ErrorState, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { MIN_OPTIMIZE_STOPS, optimizeStops, preselected } from "../domain/optimize";
import { useTripDocuments } from "../documents/DocumentsProvider";
import { type Route, useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";

type OptimizeRoute = Extract<Route, { name: "optimize" }>;
type Scope = "within_days" | "across_days";

const SCOPES: { key: Scope; title: string; detail: string }[] = [
  {
    key: "within_days",
    title: "Reorder within each day",
    detail: "No stop changes day. Each day is put in the shortest order Detour can find.",
  },
  {
    key: "across_days",
    title: "Reorder across all days",
    detail:
      "Places to visit may also move to another day. Restaurants and cafés stay on their day.",
  },
];

/**
 * Optimize a hand-made trip (ADR 029): choose how far the order may change and which stops stay
 * exactly where they are, then see the proposal. The stops a document is about start selected,
 * because their tickets fix them: the server cannot see documents, so this screen names them.
 */
export function OptimizeScreen({ route }: { route: OptimizeRoute }) {
  const nav = useNavigation();
  const actions = useChangeActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const plan = useResource<Itinerary>(
    keys.itinerary(route.itineraryId),
    (c) =>
      call(
        c.GET("/v1/itineraries/{itinerary_id}", {
          params: { path: { itinerary_id: route.itineraryId } },
        }),
      ),
    { ttlMs: 10 * 60_000 },
  );
  const documents = useTripDocuments(route.tripId);
  const [scope, setScope] = useState<Scope>("within_days");
  const [kept, setKept] = useState<Set<string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const trip = trips.data?.find((t) => t.id === route.tripId);
  if (plan.data === undefined || documents.documents === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Optimize" onBack={nav.back} />
        {plan.status === "error" ? (
          <ErrorState text={describeError(plan.error)} onRetry={plan.refresh} />
        ) : (
          <LoadingState text="Loading the plan…" />
        )}
      </View>
    );
  }
  const stops = optimizeStops(plan.data.days, documents.documents);
  if (stops.length < MIN_OPTIMIZE_STOPS) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Optimize" onBack={nav.back} />
        <EmptyState
          title="Add a few more stops first"
          text={`Optimize needs at least ${MIN_OPTIMIZE_STOPS} stops with a place to find a shorter order.`}
        />
      </View>
    );
  }
  const choice = kept ?? new Set(preselected(stops));
  const toggle = (id: string) => {
    const next = new Set(choice);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setKept(next);
  };

  const preview = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const change = await actions.previewOptimize(route.itineraryId, {
        scope,
        fixed_item_ids: stops.filter((s) => !s.locked && choice.has(s.id)).map((s) => s.id),
      });
      nav.replace({
        name: "changePreview",
        tripId: route.tripId,
        itineraryId: route.itineraryId,
        changeSetId: change.id,
      });
    } catch (e) {
      setProblem(
        e instanceof ApiError && e.code === "no_better_order"
          ? "Your stops are already in a short order: Detour found nothing shorter. Nothing was changed."
          : describeError(e),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <ScreenHeader
        title="Optimize"
        subtitle={trip?.title ?? "Find a shorter order"}
        onBack={nav.back}
      />
      <View style={styles.pad}>
        <Text style={styles.intro}>
          Detour looks for an order of your stops with less travel. You see the result and the
          saving first; nothing changes until you accept.
        </Text>
        <View accessibilityRole="radiogroup" style={styles.group}>
          {SCOPES.map((s) => {
            const on = scope === s.key;
            return (
              <Pressable
                key={s.key}
                accessibilityRole="radio"
                accessibilityState={{ selected: on }}
                accessibilityLabel={`${s.title}. ${s.detail}`}
                testID={`scope-${s.key}`}
                onPress={() => setScope(s.key)}
                style={[styles.choice, on && styles.choiceOn]}
              >
                <Text style={styles.choiceTitle}>{s.title}</Text>
                <Text style={styles.small}>{s.detail}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={styles.heading} accessibilityRole="header">
          Keep in place
        </Text>
        <Text style={styles.small}>
          These stops keep their day and time. Stops with a document are selected, because a ticket
          usually fixes the time; locked stops always stay.
        </Text>
        <Card>
          {stops.map((s) => {
            const on = s.locked || choice.has(s.id);
            return (
              <Pressable
                key={s.id}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on, disabled: s.locked }}
                accessibilityLabel={`${s.name}, day ${s.day}${s.locked ? ", locked" : s.hasDocument ? ", has a document" : ""}`}
                testID={`keep-${s.id}`}
                disabled={s.locked}
                onPress={() => toggle(s.id)}
                style={styles.stop}
              >
                <View style={[styles.box, on && styles.boxOn]}>
                  {on ? <Text style={styles.tick}>✓</Text> : null}
                </View>
                <View style={styles.stopBody}>
                  <Text style={styles.stopName}>{s.name}</Text>
                  <Text style={styles.small}>
                    {`Day ${s.day}${s.locked ? " · locked" : s.hasDocument ? " · has a document" : ""}`}
                  </Text>
                </View>
              </Pressable>
            );
          })}
        </Card>
        <Text style={styles.small}>
          Opening hours are not known, and restaurants and cafés stay on their day within an hour of
          the time you chose.
        </Text>
        {problem ? <Notice tone="error">{problem}</Notice> : null}
        <Button
          label="Show a shorter order"
          testID="optimize-run"
          fill
          loading={busy}
          disabled={busy || !actions.connected}
          onPress={() => void preview()}
        />
        {!actions.connected ? (
          <Notice tone="info">Optimize needs a connection to the server.</Notice>
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  pad: { paddingHorizontal: spacing.lg, gap: spacing.md },
  intro: { ...type.body, color: colors.text },
  group: { gap: spacing.sm },
  choice: {
    minHeight: TOUCH,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.outline,
    gap: spacing.xs,
  },
  choiceOn: { borderColor: colors.primary, borderWidth: 2 },
  choiceTitle: { ...type.body, color: colors.text, fontWeight: "600" },
  heading: { ...type.heading, color: colors.text },
  small: { ...type.small, color: colors.muted },
  stop: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: TOUCH,
    paddingVertical: spacing.xs,
  },
  stopBody: { flex: 1 },
  stopName: { ...type.body, color: colors.text },
  box: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  boxOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  tick: { color: colors.surface, fontSize: 14, fontWeight: "700" },
});
