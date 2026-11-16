import type { Trip } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import {
  Button,
  ConfirmSheet,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  ScreenHeader,
  Section,
} from "../components/ds";
import { keys, useTripActions } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useDocumentActions } from "../documents/DocumentsProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";
import { formatTripSpan } from "../util/format";

/** Settings of one trip: ask for new proposals, or delete the trip. */
export function TripSettingsScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const actions = useTripActions();
  const documents = useDocumentActions();
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
      // The proposals are the screen to see now; going back from it returns to the trip.
      nav.resetTo([
        { name: "trips" },
        { name: "tripOverview", tripId: trip.id },
        { name: "trip", tripId: trip.id },
      ]);
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
      // The trip stays as it is; going back returns to the trips.
      nav.resetTo([{ name: "trips" }, { name: "tripOverview", tripId: trip.id }]);
    } catch (e) {
      // Close the sheet so the problem is in view.
      setConfirmArchive(false);
      setProblem(describeError(e));
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("delete");
    setProblem(null);
    try {
      await actions.deleteTrip(trip);
      // The trip's documents live on this phone only (ADR 023): they go with the trip.
      await documents.removeTrip(trip.id).catch(() => undefined);
      nav.switchRoot({ name: "trips" });
    } catch (e) {
      setConfirmDelete(false);
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
        <View style={styles.body}>
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {!actions.connected ? (
            <Notice tone="info">Changes to a trip need a connection to the server.</Notice>
          ) : null}

          {trip.destination.kind === "route" ? (
            <Section title="Your cities">
              <Text style={styles.text}>
                {`${(trip.stops ?? []).map((x) => `${x.name} (${x.days})`).join(", ")}. Add, remove or reorder cities and change their days. ${
                  hasPlan
                    ? "You see what changes in your plan before anything is saved."
                    : "The proposals are made again for the new cities."
                }`}
              </Text>
              <Button
                testID="edit-stops"
                label="Edit cities"
                variant="secondary"
                size="sm"
                disabled={!actions.connected || busy !== null}
                onPress={() => nav.push({ name: "editStops", tripId: trip.id })}
              />
            </Section>
          ) : null}

          {trip.destination.kind !== "place" ? (
            <Section title="Proposals">
              <Text style={styles.text}>
                {hasPlan
                  ? "Ask Detour for two new proposals and choose again. Your current plan, with the places you added, stays selected until you choose another."
                  : "Ask Detour for two new proposals to compare."}
              </Text>
              <Button
                testID="regenerate"
                label="Get new proposals"
                variant="secondary"
                size="sm"
                loading={busy === "generate"}
                disabled={!actions.connected || busy !== null}
                onPress={() => void regenerate()}
              />
              {busy === "generate" ? (
                <Text style={styles.note}>Planning… this usually takes a few seconds.</Text>
              ) : null}
            </Section>
          ) : null}

          {!past ? (
            <Section title="Mark as a past trip">
              <Text style={styles.text}>
                A trip also becomes a past trip by itself two days after its last day, when it has
                dates. It moves to the Past tab and keeps its plan, routes and documents, and you
                can still change it. Only the undo history is cut to the last five changes.
              </Text>
              <Button
                testID="archive-trip"
                label="Mark as past trip"
                variant="secondary"
                tone="danger"
                size="sm"
                disabled={!actions.connected || busy !== null}
                accessibilityLabel={`Mark the trip ${trip.title} as a past trip`}
                onPress={() => setConfirmArchive(true)}
              />
            </Section>
          ) : null}

          <Section title="Delete this trip">
            <Text style={styles.text}>
              Removes the trip, all its plans and its documents on this phone for good. This cannot
              be undone.
            </Text>
            <Button
              testID="delete-trip"
              label="Delete trip"
              variant="secondary"
              tone="danger"
              size="sm"
              disabled={!actions.connected || busy !== null}
              accessibilityLabel={`Delete the trip ${trip.title}`}
              onPress={() => setConfirmDelete(true)}
            />
          </Section>
        </View>
      </ScrollView>

      <ConfirmSheet
        visible={confirmArchive}
        title="Mark as a past trip?"
        message={`“${trip.title}” moves to the Past tab. Its plan stays, and the undo history is cut to the last five changes.`}
        confirmLabel="Yes, mark as past"
        cancelLabel="Not yet"
        confirmTestID="confirm-archive"
        busy={busy === "archive"}
        onConfirm={() => void markPast()}
        onCancel={() => setConfirmArchive(false)}
      />
      <ConfirmSheet
        visible={confirmDelete}
        title="Delete this trip?"
        message={`“${trip.title}” and all its plans will be deleted.`}
        confirmLabel="Yes, delete the trip"
        cancelLabel="Keep the trip"
        confirmTestID="confirm-delete"
        busy={busy === "delete"}
        onConfirm={() => void remove()}
        onCancel={() => setConfirmDelete(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  body: { paddingHorizontal: layout.gutter, gap: layout.section },
  text: { ...type.label, color: colors.text },
  note: { ...type.caption, color: colors.muted },
});
