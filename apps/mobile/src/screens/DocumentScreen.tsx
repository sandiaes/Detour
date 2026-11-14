import type { Trip } from "@detour/shared";
import { useState } from "react";
import { Image, ScrollView, StyleSheet, Text, View } from "react-native";

import { call } from "../api/unwrap";
import { Button } from "../components/Button";
import { CATEGORY_ICON } from "../components/documents/DocumentList";
import { Icon } from "../components/ds/Icon";
import { Badge } from "../components/ds/primitives";
import { EmptyState, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useDocument, useDocumentActions } from "../documents/DocumentsProvider";
import { CannotOpenError } from "../documents/files";
import { CATEGORY_LABEL, fileLine, linkLabel } from "../documents/model";
import { localToday } from "../domain/trips";
import { useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { formatDate } from "../util/format";

/** One document (ADR 023): what it is, what it is about, the file; open, edit or delete it. */
export function DocumentScreen({ tripId, documentId }: { tripId: string; documentId: string }) {
  const nav = useNavigation();
  const doc = useDocument(documentId);
  const actions = useDocumentActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (doc === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Document" onBack={nav.back} />
        <LoadingState text="Loading the document…" />
      </View>
    );
  }
  if (doc === null) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Document" onBack={nav.back} />
        <EmptyState
          title="Document not found"
          text="It may have been deleted."
          action={{ label: "Back", onPress: nav.back }}
        />
      </View>
    );
  }

  const open = async () => {
    setProblem(null);
    try {
      await actions.open(doc);
    } catch (e) {
      setProblem(
        e instanceof CannotOpenError ? e.message : "The document could not be opened. Try again.",
      );
    }
  };

  const remove = async () => {
    setBusy(true);
    setProblem(null);
    try {
      await actions.remove(doc);
      nav.back();
    } catch {
      setProblem("The document could not be deleted. Try again.");
      setBusy(false);
    }
  };

  const image = doc.mimeType.startsWith("image/");
  const facts: [string, string][] = [
    ["About", linkLabel(doc.link, trip?.start_date ?? null)],
    ["File", doc.fileName],
    ["Type and size", fileLine(doc)],
    ["Added", formatDate(localToday(new Date(doc.createdAt)))],
  ];

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content}>
        <ScreenHeader title={doc.title} subtitle={trip?.title} onBack={nav.back} />
        <View style={styles.body}>
          <View style={styles.kind}>
            <Icon name={CATEGORY_ICON[doc.category]} size={18} color={colors.primary} />
            <Badge label={CATEGORY_LABEL[doc.category]} tone="primary" />
          </View>
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {image ? (
            <Image
              source={{ uri: doc.uri }}
              style={styles.preview}
              resizeMode="contain"
              accessibilityLabel={`Picture of ${doc.title}`}
              testID="document-image"
            />
          ) : null}
          <View>
            {facts.map(([label, value]) => (
              <View
                key={label}
                style={styles.fact}
                accessible
                accessibilityLabel={`${label}: ${value}`}
              >
                <Text style={styles.factLabel}>{label}</Text>
                <Text style={styles.factValue}>{value}</Text>
              </View>
            ))}
          </View>
          <View style={styles.actions}>
            <Button
              label="Open"
              icon="document"
              variant="ink"
              testID="open-document"
              hint="Shows the file with the phone's viewer"
              onPress={() => void open()}
            />
            <Button
              label="Edit"
              variant="secondary"
              testID="edit-document"
              onPress={() => nav.push({ name: "documentForm", tripId, documentId: doc.id })}
            />
          </View>
          {confirm ? (
            <View style={styles.confirm}>
              <Notice tone="error" label="Delete this document?">
                {`“${doc.title}” and its file will be removed from this phone.`}
              </Notice>
              <Button
                label="Yes, delete it"
                testID="confirm-delete-document"
                loading={busy}
                onPress={() => void remove()}
              />
              <Button label="Keep it" variant="secondary" onPress={() => setConfirm(false)} />
            </View>
          ) : (
            <Button
              label="Delete"
              variant="quiet"
              testID="delete-document"
              accessibilityLabel={`Delete the document ${doc.title}`}
              onPress={() => setConfirm(true)}
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
  body: { paddingHorizontal: spacing.lg, gap: spacing.lg },
  kind: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  preview: {
    width: "100%",
    height: 320,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
  },
  fact: {
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    gap: spacing.xxs,
  },
  factLabel: { ...type.caption, color: colors.muted },
  factValue: { ...type.body, color: colors.text },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  confirm: { gap: spacing.sm },
});
