import type { Trip } from "@detour/shared";
import { useState } from "react";
import { Image, ScrollView, StyleSheet, View } from "react-native";

import { call } from "../api/unwrap";
import { KindTile } from "../components/documents/DocumentList";
import {
  Badge,
  Button,
  ConfirmSheet,
  EmptyState,
  InfoRow,
  LoadingState,
  Notice,
  ScreenHeader,
} from "../components/ds";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useDocument, useDocumentActions } from "../documents/DocumentsProvider";
import { CannotOpenError } from "../documents/files";
import { CATEGORY_LABEL, fileLine, linkLabel } from "../documents/model";
import { localToday } from "../domain/trips";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, radius, spacing } from "../theme";
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
  const [sharing, setSharing] = useState<"share" | "unshare" | null>(null);
  const [confirmUnshare, setConfirmUnshare] = useState(false);
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

  // Where the document is (ADR 034, step 6): shared with the trip, or on this phone only.
  const share = async () => {
    setSharing("share");
    setProblem(null);
    try {
      await actions.share(doc);
    } catch (e) {
      setProblem(
        `It stays on this phone only for now: ${e instanceof Error ? e.message : "the upload failed."}`,
      );
    } finally {
      setSharing(null);
    }
  };

  const unshare = async () => {
    setSharing("unshare");
    setProblem(null);
    try {
      await actions.unshare(doc);
      setConfirmUnshare(false);
    } catch {
      setConfirmUnshare(false);
      setProblem("The upload could not be removed. Check the connection and try again.");
    } finally {
      setSharing(null);
    }
  };

  const remove = async () => {
    setBusy(true);
    setProblem(null);
    try {
      await actions.remove(doc);
      nav.back();
    } catch {
      setConfirm(false);
      setProblem("The document could not be deleted. Try again.");
      setBusy(false);
    }
  };

  const image = doc.mimeType.startsWith("image/");
  const facts: [string, string][] = [
    ["About", linkLabel(doc.link, trip?.start_date ?? null)],
    ["File", doc.fileName],
    ["Type and size", fileLine(doc)],
    ...(doc.date ? ([["Date", formatDate(doc.date)]] as [string, string][]) : []),
    ...(doc.notes ? ([["Notes", doc.notes]] as [string, string][]) : []),
    ["Added", formatDate(localToday(new Date(doc.createdAt)))],
    [
      "Kept",
      !doc.serverId
        ? "On this phone only"
        : doc.uri
          ? "Shared with the trip, and on this phone"
          : "Shared with the trip; downloaded when you open it",
    ],
  ];

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content}>
        <ScreenHeader title={doc.title} subtitle={trip?.title} onBack={nav.back} />
        <View style={styles.body}>
          <View style={styles.kind}>
            <KindTile category={doc.category} size="sm" />
            <Badge label={CATEGORY_LABEL[doc.category]} tone="primary" />
          </View>
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {image && doc.uri ? (
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
              <InfoRow key={label} label={label} value={value} />
            ))}
          </View>
          <View style={styles.actions}>
            <Button
              label="Open"
              icon="document"
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
          {doc.serverId ? (
            <Button
              label="Keep on this phone only"
              variant="secondary"
              size="sm"
              testID="unshare-document"
              loading={sharing === "unshare"}
              disabled={sharing !== null}
              onPress={() => setConfirmUnshare(true)}
            />
          ) : doc.uri ? (
            <Button
              label="Upload to the trip"
              icon="export"
              variant="secondary"
              size="sm"
              testID="share-document"
              hint="Everyone on this trip gets it"
              loading={sharing === "share"}
              disabled={sharing !== null}
              onPress={() => void share()}
            />
          ) : null}
          <Button
            label="Delete"
            variant="ghost"
            tone="danger"
            size="sm"
            testID="delete-document"
            accessibilityLabel={`Delete the document ${doc.title}`}
            onPress={() => setConfirm(true)}
          />
        </View>
      </ScrollView>
      <ConfirmSheet
        visible={confirm}
        title="Delete this document?"
        message={
          doc.serverId
            ? `“${doc.title}” will be deleted for everyone on this trip, and from this phone.`
            : `“${doc.title}” and its file will be removed from this phone.`
        }
        confirmLabel="Yes, delete it"
        cancelLabel="Keep it"
        confirmTestID="confirm-delete-document"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setConfirm(false)}
      />
      <ConfirmSheet
        visible={confirmUnshare}
        title="Keep it on this phone only?"
        message={`The uploaded copy of “${doc.title}” is deleted, so the others on this trip no longer have it. Your copy here stays.`}
        confirmLabel="Keep on this phone only"
        confirmTestID="confirm-unshare-document"
        busy={sharing === "unshare"}
        onConfirm={() => void unshare()}
        onCancel={() => setConfirmUnshare(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  body: { paddingHorizontal: layout.gutter, gap: layout.section },
  kind: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  preview: {
    width: "100%",
    height: 320,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
});
