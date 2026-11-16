import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { describeError } from "../api/unwrap";
import {
  Button,
  InlineStatus,
  ListRow,
  Notice,
  RowGroup,
  ScreenHeader,
  SectionHeader,
} from "../components/ds";
import { ArchiveError, type ReadArchive, describeFile } from "../exchange/archive";
import { type ImportOutcome, useExchange } from "../exchange/useExchange";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * Import a trip file (ADR 028): choose a file (or arrive here by opening one), see what it holds,
 * confirm. Every trip comes in as a new copy, so importing twice gives two trips.
 */
export function ImportScreen({ uri }: { uri?: string }) {
  const nav = useNavigation();
  const exchange = useExchange();
  const [read, setRead] = useState<ReadArchive | null>(null);
  const [busy, setBusy] = useState<"reading" | "importing" | null>(uri ? "reading" : null);
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<ImportOutcome | null>(null);

  const load = (target: string) =>
    exchange
      .readFile(target)
      .then(setRead, (e: unknown) =>
        setProblem(e instanceof ArchiveError ? e.message : describeError(e)),
      )
      .finally(() => setBusy(null));

  const open = (target: string) => {
    setBusy("reading");
    setProblem(null);
    setRead(null);
    return load(target);
  };

  useEffect(() => {
    // A file the app was opened with: the first state is already "reading".
    if (uri) void load(uri);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uri]);

  const choose = async () => {
    setProblem(null);
    try {
      const picked = await exchange.pick();
      if (picked) await open(picked.uri);
    } catch (e) {
      setProblem(describeError(e));
    }
  };

  const run = async () => {
    if (!read) return;
    setBusy("importing");
    setProblem(null);
    try {
      setDone(await exchange.importArchive(read));
      setRead(null);
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(null);
    }
  };

  const summary = read ? describeFile(read) : null;

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content}>
        <ScreenHeader title="Import a trip" onBack={nav.back} />
        <View style={styles.pad}>
          {!read && !done ? (
            <Text style={styles.body}>
              Choose a .detour file that Detour exported. Its trips are added to your trips as new
              copies; nothing you have is changed or replaced.
            </Text>
          ) : null}
          {busy === "reading" ? <InlineStatus busy text="Reading the file…" /> : null}
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {!exchange.connected ? (
            <Notice tone="info">Importing needs a connection to the server.</Notice>
          ) : null}

          {summary ? (
            <>
              <SectionHeader title="In this file" />
              <RowGroup>
                {summary.trips.map((t, n) => (
                  <ListRow
                    key={n}
                    icon="trips"
                    title={t.title}
                    detail={`${t.destination} · ${plural(t.days, "day", "days")} · ${
                      t.past
                        ? `past trip, ${plural(t.stops, "stop", "stops")} kept`
                        : plural(t.stops, "stop", "stops")
                    }`}
                    inset="none"
                    trailing={null}
                  />
                ))}
              </RowGroup>
              <Text style={styles.small}>
                {summary.documents > 0
                  ? `${plural(summary.documents, "document", "documents")} come with the trips.`
                  : "No documents are in this file."}
                {summary.albums > 0
                  ? ` ${plural(summary.albums, "photo album link", "photo album links")} too.`
                  : ""}
                {read && read.skipped.length > 0
                  ? ` ${plural(read.skipped.length, "document", "documents")} named in it cannot be read.`
                  : ""}
              </Text>
              <Button
                testID="import-run"
                label={summary.trips.length === 1 ? "Import this trip" : "Import these trips"}
                icon="export"
                loading={busy === "importing"}
                disabled={!exchange.connected || summary.trips.length === 0}
                onPress={run}
              />
            </>
          ) : null}

          {done ? (
            <>
              <Notice tone="info" label="Imported">
                {`${plural(done.trips.length, "trip", "trips")} added${
                  done.documents > 0
                    ? ` with ${plural(done.documents, "document", "documents")}`
                    : ""
                }.`}
              </Notice>
              {done.notRestored.length > 0 ? (
                <Notice tone="warning" label="Not restored">
                  {`These could not be restored: ${done.notRestored.join(", ")}.`}
                </Notice>
              ) : null}
              <Button
                testID="import-open"
                label={done.trips.length === 1 ? "Open the trip" : "Show my trips"}
                onPress={() => {
                  const only = done.trips.length === 1 ? done.trips[0] : undefined;
                  if (only) {
                    nav.resetTo([{ name: "trips" }, { name: "tripOverview", tripId: only.tripId }]);
                  } else {
                    nav.switchRoot({ name: "trips" });
                  }
                }}
              />
            </>
          ) : (
            <Button
              testID="import-choose"
              label={read ? "Choose another file" : "Choose a file"}
              variant={read ? "secondary" : "primary"}
              disabled={busy !== null}
              onPress={choose}
            />
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  pad: { paddingHorizontal: layout.gutter, gap: layout.section },
  body: { ...type.label, color: colors.text },
  small: { ...type.caption, color: colors.muted },
});
