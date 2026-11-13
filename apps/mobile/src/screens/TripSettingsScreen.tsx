import type { Trip } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Card, EmptyState, ErrorState, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys, useTripActions } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, spacing, type } from "../theme";
import { formatTripSpan } from "../util/format";

/** Settings of one trip: ask for new proposals, or delete the trip. */
export function TripSettingsScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const actions = useTripActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const [busy, setBusy] = useState<"generate" | "delete" | "archive" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (trips.data === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Trip settings" onBack={nav.back} />
        {trips.status === "error" ? (
          <ErrorState text={describeError(trips.error)} onRetry={trips.refresh} />
        ) : (
          <LoadingState text="Loading the trip…" />
        )}
      </View>
    );
  }
  if (!trip) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Trip settings" onBack={nav.back} />
        <EmptyState
          title="Trip not found"
          text="It may have been deleted."
          action={{ label: "Back to trips", onPress: () => nav.switchRoot({ name: "trips" }) }}
        />
      </View>
    );
  }

  const past = trip.status === "past";
  const hasPlan = trip.selected_itinerary_id !== null;

  const regenerate = async () => {
    setBusy("generate");
    setProblem(null);
    try {
      await actions.generate(trip.id);
      // The proposals are the screen to see now; going back from it returns to the trips.
      nav.resetTo([{ name: "trips" }, { name: "trip", tripId: trip.id }]);
    } catch (e) {
      setProblem(describeError(e));
      setBusy(null);
    }
  };

  const markPast = async () => {
    setBusy("archive");
    setProblem(null);
    try {
      await actions.archiveTrip(trip);
      // The places are the screen to see now; going back from it returns to the trips.
      nav.resetTo([{ name: "trips" }, { name: "pastTrip", tripId: trip.id }]);
    } catch (e) {
      setProblem(describeError(e));
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("delete");
    setProblem(null);
    try {
      await actions.deleteTrip(trip);
      nav.switchRoot({ name: "trips" });
    } catch (e) {
      setProblem(describeError(e));
      setBusy(null);
    }
  };

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content}>
        <ScreenHeader
          title="Trip settings"
          subtitle={`${trip.title} · ${formatTripSpan(trip.start_date, trip.end_date, trip.duration_days)}`}
          onBack={nav.back}
        />
        {problem ? <Notice tone="error">{problem}</Notice> : null}
        {!actions.connected ? (
          <Notice tone="info">Changes to a trip need a connection to the server.</Notice>
        ) : null}

        {!past ? (
          <View style={styles.pad}>
            <Card>
              <Text accessibilityRole="header" style={styles.heading}>
                Proposals
              </Text>
              <Text style={styles.body}>
                {hasPlan
                  ? "Ask Detour for two new proposals and choose again. Your current plan, with the places you added, stays selected until you choose another."
                  : "Ask Detour for two new proposals to compare."}
              </Text>
              <Button
                testID="regenerate"
                label="Get new proposals"
                variant="secondary"
                loading={busy === "generate"}
                disabled={!actions.connected || busy !== null}
                onPress={() => void regenerate()}
              />
              {busy === "generate" ? (
                <Text style={styles.note}>Planning… this usually takes a few seconds.</Text>
              ) : null}
            </Card>
          </View>
        ) : null}

        {!past ? (
          <View style={styles.pad}>
            <Card>
              <Text accessibilityRole="header" style={styles.heading}>
                Mark as a past trip
              </Text>
              <Text style={styles.body}>
                {`A trip also becomes a past trip by itself two days after its last day, when it has dates. Detour keeps the title, destination, dates and ${
                  hasPlan
                    ? "the cities and attractions of your chosen plan"
                    : trip.destination.kind === "city"
                      ? "the destination city (no plan is chosen, so nothing else)"
                      : "nothing else (no plan is chosen, so no cities or attractions)"
                }, and shows them on a map. It deletes the plans, routes and travel times. Meals and restaurants are not kept. This cannot be undone.`}
              </Text>
              {confirmArchive ? (
                <View style={styles.confirm}>
                  <Notice tone="error" label="Mark as a past trip?">
                    {`“${trip.title}” will lose its plans for good.`}
                  </Notice>
                  <Button
                    testID="confirm-archive"
                    label="Yes, mark as past"
                    loading={busy === "archive"}
                    disabled={busy !== null}
                    onPress={() => void markPast()}
                  />
                  <Button
                    label="Keep planning"
                    variant="secondary"
                    disabled={busy !== null}
                    onPress={() => setConfirmArchive(false)}
                  />
                </View>
              ) : (
                <Button
                  testID="archive-trip"
                  label="Mark as past trip"
                  variant="secondary"
                  disabled={!actions.connected || busy !== null}
                  accessibilityLabel={`Mark the trip ${trip.title} as a past trip`}
                  onPress={() => setConfirmArchive(true)}
                />
              )}
            </Card>
          </View>
        ) : null}

        <View style={styles.pad}>
          <Card>
            <Text accessibilityRole="header" style={styles.heading}>
              Delete this trip
            </Text>
            <Text style={styles.body}>
              {past
                ? "Removes the trip and its saved places from Detour for good. This cannot be undone."
                : "Removes the trip and all its plans from Detour for good. This cannot be undone."}
            </Text>
            {confirmDelete ? (
              <View style={styles.confirm}>
                <Notice tone="error" label="Delete this trip?">
                  {`“${trip.title}” and all its plans will be deleted.`}
                </Notice>
                <Button
                  testID="confirm-delete"
                  label="Yes, delete the trip"
                  loading={busy === "delete"}
                  disabled={busy !== null}
                  onPress={() => void remove()}
                />
                <Button
                  label="Keep the trip"
                  variant="secondary"
                  disabled={busy !== null}
                  onPress={() => setConfirmDelete(false)}
                />
              </View>
            ) : (
              <Button
                testID="delete-trip"
                label="Delete trip"
                variant="secondary"
                disabled={!actions.connected || busy !== null}
                accessibilityLabel={`Delete the trip ${trip.title}`}
                onPress={() => setConfirmDelete(true)}
              />
            )}
          </Card>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl, gap: spacing.md },
  pad: { paddingHorizontal: spacing.lg },
  heading: { ...type.heading, color: colors.text },
  body: { ...type.body, color: colors.text },
  note: { ...type.small, color: colors.muted },
  confirm: { gap: spacing.sm },
});
