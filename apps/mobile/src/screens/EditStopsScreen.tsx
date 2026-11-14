import type { Trip } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { StopList, type StopDraft, stopsProblem } from "../components/StopList";
import { EmptyState, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys, useTripActions } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, spacing, type } from "../theme";

/**
 * A multi-city trip's cities (ADR 024, decision 19): add, remove, reorder, change days. With a
 * chosen plan the change is previewed first (the change preview screen shows what each city keeps
 * and what leaves with a removed day); without one the cities are replaced at once.
 */
export function EditStopsScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const actions = useTripActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const [draft, setDraft] = useState<StopDraft[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (!trip) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Edit cities" onBack={nav.back} />
        {trips.data === undefined ? (
          <LoadingState text="Loading the trip…" />
        ) : (
          <EmptyState title="Trip not found" text="It may have been deleted." />
        )}
      </View>
    );
  }
  const current = trip.stops ?? [];
  const stops: StopDraft[] =
    draft ??
    current.map((x) => ({
      cityId: x.city_id,
      name: x.name,
      detail: x.country_iso2 ?? "",
      days: x.days,
    }));
  const invalid = stopsProblem(stops);
  const hasPlan = trip.selected_itinerary_id !== null;
  const unchanged =
    draft === null ||
    (draft.length === current.length &&
      draft.every((d, i) => d.cityId === current[i]?.city_id && d.days === current[i]?.days));

  const save = async () => {
    setBusy(true);
    setProblem(null);
    const body = stops.map((x) => ({ city_id: x.cityId, days: x.days }));
    try {
      if (hasPlan && trip.selected_itinerary_id) {
        const change = await actions.previewStops(trip.id, body);
        nav.replace({
          name: "changePreview",
          tripId: trip.id,
          itineraryId: trip.selected_itinerary_id,
          changeSetId: change.id,
        });
      } else {
        await actions.replaceStops(trip.id, body);
        nav.back();
      }
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <ScreenHeader title="Edit cities" subtitle={trip.title} onBack={nav.back} />
        <View style={styles.pad}>
          <StopList stops={stops} onChange={setDraft} />
          <Text style={styles.note}>
            {hasPlan
              ? "Cities you keep keep their days and places. A removed city's places leave the plan with its days; you see them before anything changes."
              : "The trip has no chosen plan yet: the new cities are saved at once."}
          </Text>
          {invalid ? (
            <Notice tone="warning" label="Cities">
              {invalid}
            </Notice>
          ) : null}
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          <Button
            testID="save-stops"
            label={hasPlan ? "Preview the change" : "Save cities"}
            variant="ink"
            fill
            loading={busy}
            disabled={unchanged || invalid !== null || !actions.connected || busy}
            onPress={() => void save()}
          />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  pad: { paddingHorizontal: spacing.lg, gap: spacing.md },
  note: { ...type.caption, color: colors.muted },
});
