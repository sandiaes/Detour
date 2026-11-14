import type { Trip } from "@detour/shared";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Switch, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Card, ErrorState, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { type DocumentSummary, type ExportOutcome, useExchange } from "../exchange/useExchange";
import { useNavigation } from "../nav/Navigator";
import { colors, spacing, type } from "../theme";
import { formatBytes } from "../util/format";

/**
 * Export one trip, or every trip as a backup, as a .detour file (ADR 028). The file goes to the
 * system share sheet; Detour uploads nothing. Documents are optional and the screen says what they
 * are: tickets and bookings, unencrypted in the file.
 */
export function ExportScreen({ tripId }: { tripId?: string }) {
  const nav = useNavigation();
  const exchange = useExchange();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [include, setInclude] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<ExportOutcome | null>(null);

  const all = trips.data;
  const chosen = all === undefined ? undefined : tripId ? all.filter((t) => t.id === tripId) : all;
  const chosenKey = chosen?.map((t) => t.id).join(",");

  useEffect(() => {
    if (chosen === undefined) return;
    let current = true;
    exchange
      .documentSummary(chosen.map((t) => t.id))
      .then((s) => current && setSummary(s))
      .catch(() => current && setSummary({ count: 0, bytes: 0 }));
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosenKey]);

  const title = tripId ? "Export trip" : "Back up all trips";
  if (chosen === undefined || summary === null) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title={title} onBack={nav.back} />
        {trips.status === "error" ? (
          <ErrorState text={describeError(trips.error)} onRetry={trips.refresh} />
        ) : (
          <LoadingState text="Loading your trips…" />
        )}
      </View>
    );
  }

  const run = async () => {
    setBusy(true);
    setProblem(null);
    try {
      setDone(await exchange.exportTrips(tripId ? [tripId] : "all", include && summary.count > 0));
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const what =
    chosen.length === 1
      ? `${chosen[0]?.title ?? "The trip"}`
      : `${chosen.length} ${chosen.length === 1 ? "trip" : "trips"}`;

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content}>
        <ScreenHeader title={title} subtitle={what} onBack={nav.back} />
        <View style={styles.pad}>
          {chosen.length === 0 ? (
            <Notice tone="info" label="Nothing to export">
              You have no trips yet.
            </Notice>
          ) : (
            <>
              <Text style={styles.body}>
                Detour makes one file with the trip, its days and places, and a past trip&apos;s
                record. You choose where it goes: messages, mail, a cloud folder or your computer.
                Detour sends it nowhere. Import it on any phone to bring the trip back as a copy.
              </Text>
              {summary.count > 0 ? (
                <Card>
                  <View style={styles.row}>
                    <View style={styles.rowBody}>
                      <Text style={styles.rowTitle}>
                        {`Include documents (${formatBytes(summary.bytes)})`}
                      </Text>
                      <Text style={styles.small}>
                        {`${summary.count} ${summary.count === 1 ? "document" : "documents"} on this phone: tickets, bookings and similar papers.`}
                      </Text>
                    </View>
                    <Switch
                      accessibilityLabel={`Include documents (${formatBytes(summary.bytes)})`}
                      testID="include-documents"
                      value={include}
                      onValueChange={setInclude}
                      trackColor={{ true: colors.primary, false: colors.outline }}
                      thumbColor={colors.surface}
                    />
                  </View>
                  {include ? (
                    <Text style={styles.warning}>
                      The file is not encrypted. Whoever receives it can read these documents, so
                      send it only to yourself or to people you trust.
                    </Text>
                  ) : null}
                </Card>
              ) : null}
            </>
          )}
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {!exchange.connected ? (
            <Notice tone="info">Exporting needs a connection to the server.</Notice>
          ) : null}
          {done ? (
            <Notice tone="info" label={done.shared ? "Exported" : "File made"}>
              {`${done.fileName} holds ${done.trips} ${done.trips === 1 ? "trip" : "trips"}${
                done.documents > 0
                  ? ` and ${done.documents} ${done.documents === 1 ? "document" : "documents"}`
                  : ""
              }.${done.shared ? "" : " This phone has no way to share it."}${
                done.left.length > 0
                  ? ` Left out because they could not be read or are too large: ${done.left.join(", ")}.`
                  : ""
              }`}
            </Notice>
          ) : null}
          {chosen.length > 0 ? (
            <Button
              testID="export-run"
              label={done ? "Export again" : "Export"}
              icon="export"
              loading={busy}
              disabled={!exchange.connected}
              onPress={run}
            />
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xl },
  pad: { paddingHorizontal: spacing.lg, gap: spacing.lg },
  body: { ...type.body, color: colors.text },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  rowBody: { flex: 1, gap: spacing.xxs },
  rowTitle: { ...type.body, color: colors.text },
  small: { ...type.small, color: colors.muted },
  warning: { ...type.small, color: colors.text, marginTop: spacing.sm },
});
