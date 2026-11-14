import type { Trip } from "@detour/shared";
import { StyleSheet, Text, View } from "react-native";

import { useTripDocuments } from "../../documents/DocumentsProvider";
import {
  CATEGORY_GROUP,
  type DocCategory,
  type DocLink,
  fileLine,
  groupByCategory,
  linkLabel,
} from "../../documents/model";
import { useNavigation } from "../../nav/Navigator";
import { colors, spacing, type } from "../../theme";
import { Button } from "../Button";
import { Icon, type IconName } from "../ds/Icon";
import { ListRow, RowGroup, SectionTitle } from "../ds/primitives";
import { Notice } from "../ui";

export const CATEGORY_ICON: Record<DocCategory, IconName> = {
  ticket: "ticket",
  booking: "calendar",
  transport: "transport",
  insurance: "shield",
  other: "document",
};

/** Said wherever documents are added: where they are kept, and what that means. */
export const DEVICE_ONLY_NOTE =
  "Documents stay on this phone only. They are not uploaded, and deleting the app or the trip deletes them.";

/**
 * A trip's documents, grouped by kind (ADR 023): tickets, bookings, transport, insurance, other.
 * Each row says what it is about (the whole trip, a day, a place, a journey) and the file.
 */
export function DocumentList({
  trip,
  filter,
  addLink,
}: {
  trip: Trip;
  /** Only the documents this returns true for (a place's documents). */
  filter?: (link: DocLink) => boolean;
  /** The link a new document starts with. */
  addLink?: DocLink;
}) {
  const nav = useNavigation();
  const { documents, error, reload } = useTripDocuments(trip.id);
  const add = () => nav.push({ name: "documentForm", tripId: trip.id, link: addLink });
  const shown = documents?.filter((d) => (filter ? filter(d.link) : true));

  if (error) {
    return (
      <Notice tone="error" action={{ label: "Try again", onPress: reload }}>
        {error}
      </Notice>
    );
  }
  if (shown === undefined) {
    return <Text style={styles.muted}>Loading the documents…</Text>;
  }

  const addButton = (
    <Button
      label={filter ? "Attach a document" : "Add a document"}
      icon="add"
      variant={filter ? "secondary" : "ink"}
      testID="add-document"
      onPress={add}
    />
  );

  if (shown.length === 0) {
    if (filter) return addButton;
    return (
      <View style={styles.empty} testID="documents-empty">
        <View style={styles.emptyIcon}>
          <Icon name="document" size={28} color={colors.primary} />
        </View>
        <Text style={styles.emptyTitle}>No documents yet</Text>
        <Text style={styles.emptyText}>
          Keep tickets, bookings, transport documents and insurance with the trip, each linked to
          the whole trip, a day, a place or a journey.
        </Text>
        {addButton}
        <Text style={styles.note}>{DEVICE_ONLY_NOTE}</Text>
      </View>
    );
  }

  return (
    <View style={styles.list} testID="documents-list">
      {groupByCategory(shown).map((group) => (
        <View key={group.category} style={styles.group}>
          {filter ? null : (
            <SectionTitle title={`${CATEGORY_GROUP[group.category]} (${group.docs.length})`} />
          )}
          <RowGroup>
            {group.docs.map((doc) => (
              <ListRow
                key={doc.id}
                icon={CATEGORY_ICON[doc.category]}
                title={doc.title}
                detail={`${linkLabel(doc.link, trip.start_date)} · ${fileLine(doc)}`}
                testID={`document-${doc.id}`}
                onPress={() => nav.push({ name: "document", tripId: trip.id, documentId: doc.id })}
              />
            ))}
          </RowGroup>
        </View>
      ))}
      {addButton}
      {filter ? null : <Text style={styles.note}>{DEVICE_ONLY_NOTE}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.lg },
  group: { gap: spacing.xs },
  muted: { ...type.small, color: colors.muted },
  note: { ...type.caption, color: colors.muted },
  empty: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.lg },
  emptyIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.primarySoft,
  },
  emptyTitle: { ...type.heading, color: colors.text },
  emptyText: { ...type.small, color: colors.muted, textAlign: "center" },
});
