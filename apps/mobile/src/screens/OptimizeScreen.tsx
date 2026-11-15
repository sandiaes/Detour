import type { Itinerary, Trip } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError, call, describeError } from "../api/unwrap";
import {
  Badge,
  Button,
  Checkbox,
  ChoiceGroupTitle,
  CompactHeader,
  EmptyState,
  ErrorState,
  InlineStatus,
  ListRow,
  LoadingState,
  Notice,
  Radio,
  Sheet,
} from "../components/ds";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { MIN_OPTIMIZE_STOPS, optimizeStops, preselected } from "../domain/optimize";
import { useTripDocuments } from "../documents/DocumentsProvider";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type, weight } from "../theme";
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
          {SCOPES.map((sc) => {
            const on = scope === sc.key;
            return (
              <ListRow
                key={sc.key}
                role="radio"
                selected={on}
                checked={on}
                leading={<Radio on={on} />}
                title={sc.title}
                detail={sc.detail}
                density="compact"
                inset="none"
                trailing={null}
                accessibilityLabel={`${sc.title}. ${sc.detail}`}
                testID={`scope-${sc.key}`}
                onPress={() => setScope(sc.key)}
              />
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

        <View style={styles.pad}>
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
            <InlineStatus text="Optimize needs a connection to the server." />
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
                  {newDay ? <ChoiceGroupTitle title={`Day ${s.day}`} /> : null}
                  <ListRow
                    role="checkbox"
                    checked={on}
                    leading={<Checkbox on={on} />}
                    title={s.name}
                    density="compact"
                    inset="none"
                    disabled={s.locked}
                    disabledLabel="Locked"
                    trailing={s.hasDocument && !s.locked ? <Badge label="Document" /> : undefined}
                    accessibilityLabel={`${s.name}, day ${s.day}${s.locked ? ", locked" : s.hasDocument ? ", has a document" : ""}`}
                    testID={`keep-${s.id}`}
                    onPress={() => toggle(s.id)}
                  />
                </View>
              );
            })}
          </ScrollView>
          <Button label="Done" fill testID="keep-done" onPress={() => setPicking(false)} />
        </Sheet>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl, gap: layout.block },
  pad: { paddingHorizontal: layout.gutter, gap: spacing.sm },
  intro: { ...type.label, color: colors.muted, paddingHorizontal: layout.gutter },
  label: {
    ...type.label,
    fontWeight: weight.semibold,
    color: colors.text,
    paddingHorizontal: layout.gutter,
  },
  group: { marginHorizontal: layout.gutter },
  small: { ...type.caption, color: colors.muted },
  stops: { maxHeight: 340 },
});
