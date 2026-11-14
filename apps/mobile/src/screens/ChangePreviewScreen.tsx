import type { ChangeSet } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError, call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import {
  Card,
  ErrorState,
  LoadingState,
  Notice,
  PlanNotes,
  ScreenHeader,
  WakingServer,
} from "../components/ui";
import { changeKey, useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { diffSections, diffSummary, travelChangeText } from "../domain/changes";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, spacing, type } from "../theme";

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

  const data = change.data;
  if (data === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Preview" onBack={nav.back} />
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

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <ScreenHeader
        title={
          data.action === "edit_stops"
            ? "Change your cities?"
            : removing
              ? `Remove ${data.target_name}?`
              : `Add ${data.target_name}?`
        }
        subtitle="Nothing changes until you accept."
        onBack={nav.back}
      />
      <View style={styles.section}>
        <Card accent>
          <Text style={styles.summary} accessibilityRole="summary">
            {diffSummary(data.diff)}
          </Text>
          <Text style={styles.travel}>{travelChangeText(data.diff.travel_minutes_added)}</Text>
        </Card>
      </View>
      <PlanNotes notes={data.notes} />
      {sections.map((s) => (
        <View key={s.key} style={styles.section} testID={`diff-${s.key}`}>
          {s.warn ? (
            <Notice tone="warning" label="Left out">
              {s.lines.length === 1
                ? "This item is no longer in the plan if you accept."
                : `These ${s.lines.length} items are no longer in the plan if you accept.`}
            </Notice>
          ) : null}
          <Text style={styles.title} accessibilityRole="header">
            {s.title}
          </Text>
          {s.lines.map((line) => (
            <Text key={line} style={styles.line}>
              • {line}
            </Text>
          ))}
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
            <Button label="Back to the plan" variant="secondary" onPress={nav.back} />
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  section: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg, gap: spacing.xs },
  summary: { ...type.body, color: colors.text, fontWeight: "600" },
  travel: { ...type.small, color: colors.muted },
  title: { ...type.heading, color: colors.text },
  line: { ...type.small, color: colors.text },
  muted: { ...type.caption, color: colors.muted },
  buttons: { gap: spacing.sm },
});
