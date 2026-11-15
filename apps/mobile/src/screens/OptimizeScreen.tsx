import type { Itinerary, Trip } from "@detour/shared";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError, call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Icon } from "../components/ds/Icon";
import { ListRow, Sheet } from "../components/ds/primitives";
import { CompactHeader, EmptyState, ErrorState, LoadingState, Notice } from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { MIN_OPTIMIZE_STOPS, optimizeStops, preselected } from "../domain/optimize";
import { useTripDocuments } from "../documents/DocumentsProvider";
import { type Route, useNavigation } from "../nav/Navigator";
import { TOUCH, colors, spacing, type } from "../theme";
import { pluralise } from "../util/format";

type OptimizeRoute = Extract<Route, { name: "optimize" }>;
type Scope = "within_days" | "across_days";

const SCOPES: { key: Scope; title: string; detail: string }[] = [
  {
    key: "within_days",
    title: "Within each day",
    detail: "No stop changes day.",
  },
  {
    key: "across_days",
    title: "Across all days",
    detail: "Places to visit may move to another day. Restaurants and cafés stay on theirs.",
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
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const trip = trips.data?.find((t) => t.id === route.tripId);
  if (plan.data === undefined || documents.documents === undefined) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Optimize" onBack={nav.back} />
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
        <CompactHeader title="Optimize" onBack={nav.back} />
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
  // Locked stops always stay; the rest are the ones the user (or a document) keeps.
  const lockedCount = stops.filter((s) => s.locked).length;
  const keptCount = stops.filter((s) => !s.locked && choice.has(s.id)).length + lockedCount;
  const documented = stops.filter((s) => s.hasDocument && !s.locked && choice.has(s.id)).length;
  const keepDetail =
    keptCount === 0
      ? "Nothing is kept: every stop may move"
      : `${pluralise(keptCount, "stop")} keep their day and time${documented > 0 ? ` · ${pluralise(documented, "has a document", "have documents")}` : ""}`;

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
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content}>
        <CompactHeader title="Optimize" subtitle={trip?.title} onBack={nav.back} />
        <Text style={styles.intro}>
          Finds an order of your stops with less travel. You see the saving first; nothing changes
          until you accept.
        </Text>

        <Text style={styles.label} accessibilityRole="header">
          How far the order may change
        </Text>
        <View accessibilityRole="radiogroup" style={styles.group}>
          {SCOPES.map((s) => {
            const on = scope === s.key;
            return (
              <Pressable
                key={s.key}
                accessibilityRole="radio"
                accessibilityState={{ selected: on, checked: on }}
                accessibilityLabel={`${s.title}. ${s.detail}`}
                testID={`scope-${s.key}`}
                onPress={() => setScope(s.key)}
                style={styles.choice}
              >
                <View style={[styles.radio, on && styles.radioOn]}>
                  {on ? <View style={styles.radioDot} /> : null}
                </View>
                <View style={styles.choiceText}>
                  <Text style={styles.choiceTitle}>{s.title}</Text>
                  <Text style={styles.small}>{s.detail}</Text>
                </View>
              </Pressable>
            );
          })}
        </View>

        <ListRow
          icon="lock"
          title="Keep in place"
          detail={keepDetail}
          testID="keep-summary"
          onPress={() => setPicking(true)}
        />

        {problem ? <Notice tone="error">{problem}</Notice> : null}
        <View style={styles.pad}>
          <Button
            label="Show a shorter order"
            testID="optimize-run"
            variant="ink"
            size="compact"
            fill
            loading={busy}
            disabled={busy || !actions.connected}
            onPress={() => void preview()}
          />
          {!actions.connected ? (
            <Text style={styles.small}>Optimize needs a connection to the server.</Text>
          ) : null}
        </View>
      </ScrollView>

      {picking ? (
        <Sheet visible title="Keep in place" onClose={() => setPicking(false)}>
          <Text style={styles.small}>
            Selected stops keep their day and time. A stop with a document starts selected, because
            a ticket usually fixes the time; locked stops always stay.
          </Text>
          <ScrollView style={styles.stops}>
            {stops.map((s, i) => {
              const on = s.locked || choice.has(s.id);
              const newDay = i === 0 || stops[i - 1]?.day !== s.day;
              return (
                <View key={s.id}>
                  {newDay ? <Text style={styles.dayHead}>Day {s.day}</Text> : null}
                  <Pressable
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: on, disabled: s.locked }}
                    accessibilityLabel={`${s.name}, day ${s.day}${s.locked ? ", locked" : s.hasDocument ? ", has a document" : ""}`}
                    testID={`keep-${s.id}`}
                    disabled={s.locked}
                    onPress={() => toggle(s.id)}
                    style={styles.stop}
                  >
                    <View style={[styles.box, on && styles.boxOn]}>
                      {on ? <Icon name="check" size={14} color={colors.onPrimary} /> : null}
                    </View>
                    <Text style={styles.stopName} numberOfLines={1}>
                      {s.name}
                    </Text>
                    {s.locked || s.hasDocument ? (
                      <Text style={styles.tag}>{s.locked ? "Locked" : "Document"}</Text>
                    ) : null}
                  </Pressable>
                </View>
              );
            })}
          </ScrollView>
          <Button
            label="Done"
            variant="ink"
            size="compact"
            fill
            testID="keep-done"
            onPress={() => setPicking(false)}
          />
        </Sheet>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl, gap: spacing.md },
  pad: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  intro: { ...type.small, color: colors.muted, paddingHorizontal: spacing.lg },
  label: { ...type.small, fontWeight: "700", color: colors.text, paddingHorizontal: spacing.lg },
  group: {
    marginHorizontal: spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  choice: {
    minHeight: TOUCH,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  choiceText: { flex: 1, gap: 1 },
  choiceTitle: { ...type.small, color: colors.text, fontWeight: "600" },
  small: { ...type.caption, color: colors.muted },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  radioOn: { borderColor: colors.ink },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.ink },
  stops: { maxHeight: 340 },
  dayHead: { ...type.caption, fontWeight: "700", color: colors.muted, paddingTop: spacing.sm },
  stop: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: TOUCH,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  stopName: { ...type.small, color: colors.text, flex: 1 },
  tag: { ...type.caption, color: colors.muted },
  box: {
    width: 20,
    height: 20,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  boxOn: { backgroundColor: colors.ink, borderColor: colors.ink },
});
