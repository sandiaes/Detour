import type { ChangeSet, Itinerary } from "@detour/shared";
import { useMemo, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { ApiError, call, describeError } from "../api/unwrap";
import {
  Bullets,
  Button,
  Card,
  CompactHeader,
  ErrorState,
  LoadingState,
  Notice,
  SectionHeader,
  StatRow,
  Tabs,
  WakingServer,
} from "../components/ds";
import { PlanDayView } from "../components/plan/DayPlan";
import { PlanNotes } from "../components/plan/PlanNotes";
import { keys } from "../data/actions";
import { changeKey, useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { diffSections, diffSummary, travelChangeText } from "../domain/changes";
import { formatDistance, proposedDays, travelMeters } from "../domain/optimize";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type, weight } from "../theme";
import { formatMinutes } from "../util/format";

type PreviewRoute = Extract<Route, { name: "changePreview" }>;

const STATUS_TEXT: Record<string, string> = {
  applied: "Accepted: the plan now has this change.",
  discarded: "Discarded: the plan was not changed.",
  expired: "This preview is out of date: the plan changed after it was made. Preview again.",
};

export function ChangePreviewScreen({ route }: { route: PreviewRoute }) {
  const nav = useNavigation();
  const actions = useChangeActions();
  const change = useResource<ChangeSet>(
    changeKey(route.changeSetId),
    (c) =>
      call(
        c.GET("/v1/change-sets/{change_set_id}", {
          params: { path: { change_set_id: route.changeSetId } },
        }),
      ),
    { ttlMs: 10 * 60_000 },
  );
  const [working, setWorking] = useState<"apply" | "discard" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [view, setView] = useState<"map" | "details">("map");
  const [dayIndex, setDayIndex] = useState<number | null>(null);
  const { state: backend } = useBackend();

  const data = change.data;
  // An Optimize preview is drawn as a map of the proposed days; it needs the current plan's stops.
  const mapped = data?.action === "optimize" && data.proposed ? data.proposed : null;
  const current = useResource<Itinerary>(
    mapped ? keys.itinerary(route.itineraryId) : null,
    (c) =>
      call(
        c.GET("/v1/itineraries/{itinerary_id}", {
          params: { path: { itinerary_id: route.itineraryId } },
        }),
      ),
    { ttlMs: 10 * 60_000 },
  );
  const after = useMemo(
    () => (mapped && current.data ? proposedDays(current.data.days, mapped) : null),
    [mapped, current.data],
  );
  if (data === undefined) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Preview" onBack={nav.back} />
        {change.status === "error" ? (
          <ErrorState
            title="The preview could not be loaded"
            text={describeError(change.error)}
            onRetry={change.refresh}
          />
        ) : change.waking ? (
          <WakingServer />
        ) : (
          <LoadingState text="Loading the preview…" />
        )}
      </View>
    );
  }

  const removing = data.action === "remove_place";
  const pending = data.status === "pending";
  const sections = diffSections(data.diff);

  const accept = async () => {
    setWorking("apply");
    setProblem(null);
    try {
      await actions.apply(route.tripId, data.id);
      nav.back();
    } catch (e) {
      setProblem(describeError(e));
      if (
        e instanceof ApiError &&
        (e.code === "change_set_stale" || e.code === "change_set_closed")
      )
        change.refresh();
    } finally {
      setWorking(null);
    }
  };

  const discard = async () => {
    setWorking("discard");
    setProblem(null);
    try {
      await actions.discard(data.id);
      nav.back();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setWorking(null);
    }
  };

  if (after && current.data) {
    const metersBefore = travelMeters(current.data.days);
    const metersAfter = travelMeters(after);
    const saved = -data.diff.travel_minutes_added;
    const shorter = saved >= 0;
    const km = Math.abs(metersBefore - metersAfter);
    const first = data.diff.days_changed[0] ?? after[0]?.day_index ?? 1;
    const shownDay = dayIndex ?? first;
    return (
      <View style={styles.fill}>
        <CompactHeader
          title={data.restores_version !== null ? "Undo Optimize?" : "A shorter order?"}
          subtitle="Nothing changes until you accept."
          onBack={nav.back}
        />
        <StatRow
          stats={[
            {
              key: "time",
              icon: "clock",
              value: formatMinutes(Math.abs(saved)),
              label: shorter ? "Time saved" : "Time added",
              spoken: `${formatMinutes(Math.abs(saved))} of travel ${shorter ? "saved" : "added"}`,
            },
            {
              key: "distance",
              icon: "route",
              value: formatDistance(km),
              label: metersAfter <= metersBefore ? "Shorter" : "Longer",
              spoken: `${formatDistance(km)} ${metersAfter <= metersBefore ? "shorter" : "longer"}`,
            },
            {
              key: "days",
              icon: "calendar",
              value: data.diff.days_changed.length,
              label: data.diff.days_changed.length === 1 ? "Day changed" : "Days changed",
            },
          ]}
        />
        <Tabs
          compact
          value={view}
          onChange={setView}
          items={[
            { key: "map", label: "Map" },
            { key: "details", label: "Details" },
          ]}
        />
        <View style={styles.fill}>
          {view === "map" ? (
            <PlanDayView
              days={after}
              dayIndex={shownDay}
              onDayChange={setDayIndex}
              mode="map"
              map={backend.phase === "ready" ? backend.connection.config.map : null}
              onShowList={() => setView("details")}
            />
          ) : (
            <ScrollView contentContainerStyle={styles.details}>
              <PlanNotes notes={data.notes} defaultOpen />
              {sections.map((s) => (
                <View key={s.key} style={styles.section} testID={`diff-${s.key}`}>
                  <SectionHeader title={s.title} />
                  <Bullets items={s.lines} />
                </View>
              ))}
            </ScrollView>
          )}
        </View>
        <View style={styles.footer}>
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {pending ? (
            <View style={styles.footerButtons}>
              <View style={styles.footerButton}>
                <Button
                  label="Discard"
                  testID="discard-change"
                  variant="secondary"
                  fill
                  loading={working === "discard"}
                  disabled={working !== null}
                  hint="Leaves the plan as it is."
                  onPress={() => void discard()}
                />
              </View>
              <View style={styles.footerButton}>
                <Button
                  label="Accept"
                  testID="accept-change"
                  fill
                  loading={working === "apply"}
                  disabled={working !== null}
                  hint="Changes the plan as shown. The previous version is kept."
                  onPress={() => void accept()}
                />
              </View>
            </View>
          ) : (
            <>
              <Notice tone="info">{STATUS_TEXT[data.status] ?? data.status}</Notice>
              <Button label="Back to the plan" variant="secondary" fill onPress={nav.back} />
            </>
          )}
        </View>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <CompactHeader
        title={
          data.action === "optimize"
            ? data.restores_version !== null
              ? "Undo Optimize?"
              : "A shorter order?"
            : data.action === "edit_stops"
              ? "Change your cities?"
              : removing
                ? `Remove ${data.target_name}?`
                : `Add ${data.target_name}?`
        }
        subtitle="Nothing changes until you accept."
        onBack={nav.back}
      />
      <View style={styles.section}>
        <Card>
          <Text style={styles.summary} accessibilityRole="summary">
            {diffSummary(data.diff)}
          </Text>
          <Text style={styles.travel}>{travelChangeText(data.diff.travel_minutes_added)}</Text>
        </Card>
      </View>
      <PlanNotes notes={data.notes} defaultOpen={data.action === "optimize"} />
      {sections.map((s) => (
        <View key={s.key} style={styles.section} testID={`diff-${s.key}`}>
          {s.warn ? (
            <Notice tone="warning" label="Left out">
              {s.lines.length === 1
                ? "This item is no longer in the plan if you accept."
                : `These ${s.lines.length} items are no longer in the plan if you accept.`}
            </Notice>
          ) : null}
          <SectionHeader title={s.title} />
          <Bullets items={s.lines} />
          {s.key === "estimated" ? (
            <Text style={styles.muted}>
              Straight-line distance with a detour factor, not a measured route.
            </Text>
          ) : null}
        </View>
      ))}
      {problem ? (
        <View style={styles.section}>
          <Notice tone="error">{problem}</Notice>
        </View>
      ) : null}
      <View style={styles.section}>
        {pending ? (
          <View style={styles.buttons}>
            <Button
              label="Accept"
              testID="accept-change"
              fill
              loading={working === "apply"}
              disabled={working !== null}
              hint="Changes the plan as shown. The previous version is kept."
              onPress={() => void accept()}
            />
            <Button
              label="Discard"
              testID="discard-change"
              variant="secondary"
              fill
              loading={working === "discard"}
              disabled={working !== null}
              hint="Leaves the plan as it is."
              onPress={() => void discard()}
            />
          </View>
        ) : (
          <>
            <Notice tone="info">{STATUS_TEXT[data.status] ?? data.status}</Notice>
            <Button label="Back to the plan" variant="secondary" fill onPress={nav.back} />
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  section: { paddingHorizontal: layout.gutter, paddingBottom: layout.section, gap: spacing.sm },
  summary: { ...type.body, color: colors.text, fontWeight: weight.semibold },
  travel: { ...type.label, color: colors.muted },
  muted: { ...type.caption, color: colors.muted },
  buttons: { gap: spacing.sm },
  details: { paddingTop: spacing.sm, paddingBottom: spacing.xl },
  footer: { paddingHorizontal: layout.gutter, paddingVertical: spacing.md, gap: spacing.sm },
  footerButtons: { flexDirection: "row", gap: spacing.sm },
  footerButton: { flex: 1 },
});
