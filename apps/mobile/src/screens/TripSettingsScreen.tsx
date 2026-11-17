import type { Trip, TripMember } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { CalendarSheet } from "../components/ds/Calendar";
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
import type { PersonInfo } from "../domain/devices";
import { localToday } from "../domain/trips";
import { canShareWith, otherMembers, ownerOf, personName } from "../domain/sharing";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";
import { formatDate, formatTripSpan } from "../util/format";

/** Settings of one trip: who is on it (ADR 034), new proposals, mark as past, delete or leave. */
export function TripSettingsScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const actions = useTripActions();
  const documents = useDocumentActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  // The people you are linked to (More, People): who the trip can be shared with.
  const me = useResource<PersonInfo>("me", (c) => call(c.GET("/v1/me")), { ttlMs: 0 });
  const [busy, setBusy] = useState<
    "generate" | "delete" | "archive" | "reopen" | "share" | "leave" | "dates" | null
  >(null);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [stopSharing, setStopSharing] = useState<TripMember | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [calendar, setCalendar] = useState(false);
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
  const owner = trip.role !== "editor";
  const others = otherMembers(trip);
  const createdBy = ownerOf(trip);
  const shareable = owner ? canShareWith(trip, me.data?.people ?? []) : [];
  const hasPlan = trip.selected_itinerary_id !== null;

  const changeStart = async (iso: string | null) => {
    setCalendar(false);
    setBusy("dates");
    setProblem(null);
    try {
      await actions.setStartDate(trip, iso);
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(null);
    }
  };

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

  const reopen = async () => {
    setBusy("reopen");
    setProblem(null);
    try {
      await actions.reopenTrip(trip);
      nav.resetTo([{ name: "trips" }, { name: "tripOverview", tripId: trip.id }]);
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

  const share = async (personId: string) => {
    setBusy("share");
    setProblem(null);
    try {
      await actions.shareTrip(trip, personId);
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(null);
    }
  };

  const unshare = async (member: TripMember) => {
    setBusy("share");
    setProblem(null);
    try {
      await actions.removeMember(trip, member.person_id);
      setStopSharing(null);
    } catch (e) {
      setStopSharing(null);
      setProblem(describeError(e));
    } finally {
      setBusy(null);
    }
  };

  const leave = async () => {
    const self = (trip.members ?? []).find((m) => m.you);
    if (!self) return;
    setBusy("leave");
    setProblem(null);
    try {
      await actions.removeMember(trip, self.person_id);
      // Documents of this trip on this phone could no longer be opened from anywhere.
      await documents.removeTrip(trip.id).catch(() => undefined);
      nav.switchRoot({ name: "trips" });
    } catch (e) {
      setConfirmLeave(false);
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

          <Section title="Who's on this trip">
            {owner ? (
              <>
                <Text style={styles.text}>
                  {others.length > 0
                    ? `Shared with ${others.map((m) => personName(m.name)).join(" and ")}. Everyone on it sees and changes the plan, stays, dates and name. Only you can delete the trip or change who is on it.`
                    : "Only you. Share it with someone you are linked to and they see and change it too."}
                </Text>
                {others.map((m) => (
                  <View key={m.person_id} style={styles.member}>
                    <Text style={styles.memberName}>{personName(m.name)}</Text>
                    <Button
                      testID={`unshare-${m.person_id}`}
                      label="Stop sharing"
                      variant="ghost"
                      tone="danger"
                      size="sm"
                      disabled={!actions.connected || busy !== null}
                      accessibilityLabel={`Stop sharing this trip with ${personName(m.name)}`}
                      onPress={() => setStopSharing(m)}
                    />
                  </View>
                ))}
                {shareable.map((p) => (
                  <Button
                    key={p.person_id}
                    testID={`share-${p.person_id}`}
                    label={`Share with ${personName(p.name)}`}
                    variant="secondary"
                    size="sm"
                    loading={busy === "share"}
                    disabled={!actions.connected || busy !== null}
                    onPress={() => void share(p.person_id)}
                  />
                ))}
                {others.length === 0 && me.data && me.data.people.length === 0 ? (
                  <Button
                    testID="open-people"
                    label="Link someone under People"
                    variant="ghost"
                    size="sm"
                    onPress={() => nav.push({ name: "people" })}
                  />
                ) : null}
              </>
            ) : (
              <>
                <Text style={styles.text}>
                  {`${personName(createdBy?.name)} created this trip and shared it with you. You can change it; only ${personName(createdBy?.name)} can delete it or change who is on it.`}
                </Text>
                <Button
                  testID="leave-trip"
                  label="Leave trip"
                  variant="secondary"
                  tone="danger"
                  size="sm"
                  disabled={!actions.connected || busy !== null}
                  accessibilityLabel={`Leave the trip ${trip.title}`}
                  onPress={() => setConfirmLeave(true)}
                />
              </>
            )}
          </Section>

          {past ? (
            <Section title="Reopen this trip">
              <Text style={styles.text}>
                A past trip cannot be changed. Reopen it to edit its plan, stays, dates and name
                again. It moves back to Upcoming and does not become a past trip by itself a second
                time. Documents and photo links can be added without reopening.
              </Text>
              <Button
                testID="reopen-trip"
                label="Reopen trip"
                variant="secondary"
                size="sm"
                loading={busy === "reopen"}
                disabled={!actions.connected || busy !== null}
                accessibilityLabel={`Reopen the trip ${trip.title}`}
                onPress={() => void reopen()}
              />
            </Section>
          ) : null}

          {!past ? (
            <Section title="Trip dates">
              <Text style={styles.text}>
                {trip.start_date
                  ? `Starts ${formatDate(trip.start_date)}. Changing the start date moves every day of the plan with it. A trip whose dates are already over is not made a past trip by itself: mark it as past below.`
                  : "No start date yet. Choose one and every day of the plan gets its date."}
              </Text>
              <Button
                testID="edit-dates"
                label={trip.start_date ? "Change start date" : "Set start date"}
                variant="secondary"
                size="sm"
                loading={busy === "dates"}
                disabled={!actions.connected || busy !== null}
                onPress={() => setCalendar(true)}
              />
              <CalendarSheet
                visible={calendar}
                title="Start date"
                value={trip.start_date ?? ""}
                today={localToday()}
                onPick={(iso) => void changeStart(iso)}
                onClear={() => void changeStart(null)}
                onClose={() => setCalendar(false)}
              />
            </Section>
          ) : null}

          {!past && trip.destination.kind === "route" ? (
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

          {!past && trip.destination.kind !== "place" ? (
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
                dates. It moves to the Past tab and keeps its plan, routes and documents, but it can
                no longer be changed unless you reopen it. Documents and photo links can still be
                added. The undo history is cut to the last five changes.
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

          {owner ? (
            <Section title="Delete this trip">
              <Text style={styles.text}>
                {others.length > 0
                  ? "Removes the trip and all its plans for everyone on it, and its documents on this phone, for good. This cannot be undone."
                  : "Removes the trip, all its plans and its documents on this phone for good. This cannot be undone."}
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
          ) : null}
        </View>
      </ScrollView>

      <ConfirmSheet
        visible={confirmArchive}
        title="Mark as a past trip?"
        message={`“${trip.title}” moves to the Past tab. Its plan stays but cannot be changed unless you reopen the trip. The undo history is cut to the last five changes.`}
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
        message={
          others.length > 0
            ? `“${trip.title}” and all its plans will be deleted, also for ${others.map((m) => personName(m.name)).join(" and ")}.`
            : `“${trip.title}” and all its plans will be deleted.`
        }
        confirmLabel="Yes, delete the trip"
        cancelLabel="Keep the trip"
        confirmTestID="confirm-delete"
        busy={busy === "delete"}
        onConfirm={() => void remove()}
        onCancel={() => setConfirmDelete(false)}
      />
      <ConfirmSheet
        visible={confirmLeave}
        title="Leave this trip?"
        message={`“${trip.title}” disappears from your trips. ${personName(createdBy?.name)} keeps it. Its documents on this phone are deleted.`}
        confirmLabel="Leave trip"
        cancelLabel="Stay"
        confirmTestID="confirm-leave"
        busy={busy === "leave"}
        onConfirm={() => void leave()}
        onCancel={() => setConfirmLeave(false)}
      />
      <ConfirmSheet
        visible={stopSharing !== null}
        title="Stop sharing?"
        message={`${personName(stopSharing?.name)} will no longer see “${trip.title}”. Places they added stay in the plan.`}
        confirmLabel="Stop sharing"
        confirmTestID="confirm-unshare"
        busy={busy === "share"}
        onConfirm={() => stopSharing && void unshare(stopSharing)}
        onCancel={() => setStopSharing(null)}
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
  member: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  memberName: { ...type.body, color: colors.text },
});
