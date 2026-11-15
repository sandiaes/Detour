import type { Trip } from "@detour/shared";
import { useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useTripDocuments } from "../../documents/DocumentsProvider";
import {
  CATEGORIES,
  CATEGORY_GROUP,
  CATEGORY_HELP,
  CATEGORY_LABEL,
  type DocCategory,
  type DocLink,
  type DocSort,
  SORT_LABEL,
  type TripDocument,
  fileLine,
  groupByCategory,
  linkLabel,
  sortDocuments,
} from "../../documents/model";
import { useNavigation } from "../../nav/Navigator";
import {
  border,
  colors,
  docTones,
  opacity,
  radius,
  size as sizes,
  spacing,
  touchSlop,
  type,
  weight,
} from "../../theme";
import { formatDate } from "../../util/format";
import {
  Button,
  Chip,
  IconButton,
  type IconName,
  InlineStatus,
  ListRow,
  Notice,
  RowGroup,
  SectionHeader,
  Sheet,
  StateView,
  Tile,
} from "../ds";

export const CATEGORY_ICON: Record<DocCategory, IconName> = {
  ticket: "ticket",
  booking: "calendar",
  transport: "transport",
  other: "document",
};

/** Said wherever documents are added: where they are kept, and what that means. */
export const DEVICE_ONLY_NOTE =
  "Documents stay on this phone only. They are not uploaded, and deleting the app or the trip deletes them.";

type Filter = DocCategory | "all";

/** The tinted square that says what kind a document is (the words beside it say it too). */
export function KindTile({
  category,
  size = "md",
}: {
  category: DocCategory;
  size?: "sm" | "md" | "lg";
}) {
  const tone = docTones[category];
  return <Tile icon={CATEGORY_ICON[category]} fg={tone.fg} bg={tone.bg} size={size} />;
}

function DocumentRow({
  doc,
  trip,
  onOpen,
  onMenu,
}: {
  doc: TripDocument;
  trip: Trip;
  onOpen: () => void;
  onMenu: () => void;
}) {
  const image = doc.mimeType.startsWith("image/");
  const about = doc.date ? formatDate(doc.date) : linkLabel(doc.link, trip.start_date);
  const line = `${CATEGORY_LABEL[doc.category]} · ${fileLine(doc)}`;
  return (
    <View style={styles.row}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${doc.title}. ${line}. ${about}.`}
        onPress={onOpen}
        style={({ pressed }) => [styles.rowMain, pressed && styles.pressed]}
        testID={`document-${doc.id}`}
      >
        <KindTile category={doc.category} />
        <View style={styles.rowText}>
          <Text style={styles.rowTitle} numberOfLines={1}>
            {doc.title}
          </Text>
          <Text style={styles.rowLine} numberOfLines={1}>
            {line}
          </Text>
          <Text style={styles.rowLine} numberOfLines={1}>
            {about}
          </Text>
        </View>
        {image ? (
          <Image
            source={{ uri: doc.uri }}
            style={styles.thumb}
            resizeMode="cover"
            accessibilityIgnoresInvertColors
            testID={`document-thumb-${doc.id}`}
          />
        ) : null}
      </Pressable>
      <IconButton
        icon="dots"
        size="sm"
        label={`More for ${doc.title}`}
        testID={`document-menu-${doc.id}`}
        onPress={onMenu}
      />
    </View>
  );
}

/**
 * A trip's documents (ADR 023; reference screen 15): an empty state that offers each kind, or a
 * filterable, sortable list. Each row says what kind it is, what it is about and the file.
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
  const [kind, setKind] = useState<Filter>("all");
  const [sort, setSort] = useState<DocSort>("newest");
  const [sorting, setSorting] = useState(false);
  const [menu, setMenu] = useState<TripDocument | null>(null);
  const add = (category?: DocCategory) =>
    nav.push({ name: "documentForm", tripId: trip.id, link: addLink, category });
  const shown = documents?.filter((d) => (filter ? filter(d.link) : true));

  if (error) {
    return (
      <Notice tone="error" action={{ label: "Try again", onPress: reload }}>
        {error}
      </Notice>
    );
  }
  if (shown === undefined) {
    return <InlineStatus text="Loading the documents…" busy />;
  }

  const addButton = (
    <Button
      label="Add a document"
      icon="add"
      variant={filter ? "secondary" : "primary"}
      size={filter ? "sm" : "md"}
      fill={!filter}
      testID="add-document"
      onPress={() => add()}
    />
  );

  if (shown.length === 0) {
    if (filter) return addButton;
    return (
      <StateView
        kind="empty"
        layout="inline"
        icon="ticket"
        title="No documents yet"
        text="Add your tickets, reservations and other travel documents to keep everything in one place."
        testID="documents-empty"
      >
        <View style={styles.tiles}>
          {CATEGORIES.map((c) => (
            <Pressable
              key={c}
              accessibilityRole="button"
              accessibilityLabel={`${CATEGORY_GROUP[c]}. ${CATEGORY_HELP[c]}. Adds one.`}
              onPress={() => add(c)}
              hitSlop={touchSlop(sizes.tile + spacing.xl)}
              style={({ pressed }) => [styles.categoryTile, pressed && styles.pressed]}
              testID={`start-${c}`}
            >
              <KindTile category={c} />
              <Text style={styles.tileName} numberOfLines={1}>
                {c === "other" ? "Other" : CATEGORY_GROUP[c]}
              </Text>
            </Pressable>
          ))}
        </View>
        {addButton}
        <Text style={styles.note}>{DEVICE_ONLY_NOTE}</Text>
      </StateView>
    );
  }

  // A place's documents: a short grouped list, no filters.
  if (filter) {
    return (
      <View style={styles.list} testID="documents-list">
        {groupByCategory(shown).map((group) => (
          <RowGroup key={group.category}>
            {group.docs.map((doc) => (
              <ListRow
                key={doc.id}
                inset="none"
                icon={CATEGORY_ICON[doc.category]}
                title={doc.title}
                detail={`${linkLabel(doc.link, trip.start_date)} · ${fileLine(doc)}`}
                testID={`document-${doc.id}`}
                onPress={() => nav.push({ name: "document", tripId: trip.id, documentId: doc.id })}
              />
            ))}
          </RowGroup>
        ))}
        {addButton}
      </View>
    );
  }

  const present = new Set(shown.map((d) => d.category));
  const visible = sortDocuments(
    shown.filter((d) => kind === "all" || d.category === kind),
    sort,
  );
  return (
    <View style={styles.list} testID="documents-list">
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filters}
        accessibilityRole="tablist"
      >
        <Chip
          label="All"
          selected={kind === "all"}
          onPress={() => setKind("all")}
          testID="filter-all"
        />
        {CATEGORIES.map((c) => (
          <Chip
            key={c}
            label={CATEGORY_GROUP[c] === "Other documents" ? "Other" : CATEGORY_GROUP[c]}
            selected={kind === c}
            accessibilityLabel={`${CATEGORY_GROUP[c]}${present.has(c) ? "" : ", none yet"}`}
            onPress={() => setKind(c)}
            testID={`filter-${c}`}
          />
        ))}
      </ScrollView>
      <SectionHeader
        title={kind === "all" ? "All documents" : CATEGORY_GROUP[kind]}
        action={
          <Button
            label="Sort"
            icon="list"
            variant="ghost"
            size="sm"
            accessibilityLabel={`Sort. ${SORT_LABEL[sort]}`}
            onPress={() => setSorting(true)}
            testID="sort-documents"
          />
        }
      />
      {visible.length === 0 ? (
        <Text style={styles.muted}>
          No {CATEGORY_GROUP[kind as DocCategory].toLowerCase()} yet.
        </Text>
      ) : (
        <View style={styles.group}>
          {visible.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              trip={trip}
              onOpen={() => nav.push({ name: "document", tripId: trip.id, documentId: doc.id })}
              onMenu={() => setMenu(doc)}
            />
          ))}
        </View>
      )}
      {addButton}
      <Text style={styles.note}>{DEVICE_ONLY_NOTE}</Text>

      {sorting ? (
        <Sheet visible title="Sort documents" onClose={() => setSorting(false)}>
          <RowGroup>
            {(Object.keys(SORT_LABEL) as DocSort[]).map((s) => (
              <ListRow
                key={s}
                inset="none"
                density="compact"
                title={SORT_LABEL[s]}
                selected={s === sort}
                testID={`sort-${s}`}
                onPress={() => {
                  setSort(s);
                  setSorting(false);
                }}
              />
            ))}
          </RowGroup>
        </Sheet>
      ) : null}
      {menu ? (
        <Sheet visible title={menu.title} onClose={() => setMenu(null)}>
          <RowGroup>
            <ListRow
              inset="none"
              icon="document"
              title="Open"
              detail="Details and the file"
              testID="menu-open-document"
              onPress={() => {
                const doc = menu;
                setMenu(null);
                nav.push({ name: "document", tripId: trip.id, documentId: doc.id });
              }}
            />
            <ListRow
              inset="none"
              icon="note"
              title="Edit"
              detail="Title, kind, date, notes"
              testID="menu-edit-document"
              onPress={() => {
                const doc = menu;
                setMenu(null);
                nav.push({ name: "documentForm", tripId: trip.id, documentId: doc.id });
              }}
            />
          </RowGroup>
        </Sheet>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.md },
  muted: { ...type.label, color: colors.muted },
  note: { ...type.caption, color: colors.muted, textAlign: "center" },
  pressed: { opacity: opacity.pressed },
  filters: { gap: spacing.sm, paddingVertical: spacing.xs },
  group: { borderTopWidth: border.hairline, borderTopColor: colors.border },
  row: {
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  rowMain: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: sizes.row + spacing.sm,
    paddingVertical: spacing.sm,
  },
  rowText: { flex: 1, gap: 1 },
  rowTitle: { ...type.label, fontWeight: weight.semibold, color: colors.text },
  rowLine: { ...type.caption, color: colors.muted },
  thumb: { width: 40, height: 52, borderRadius: radius.sm, backgroundColor: colors.surfaceMuted },
  // One row: the four kinds share the width, each a small tile over its name.
  tiles: { flexDirection: "row", alignSelf: "stretch", paddingVertical: spacing.xs },
  categoryTile: {
    flex: 1,
    minHeight: sizes.tile + spacing.xl,
    alignItems: "center",
    gap: spacing.xs,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
  },
  tileName: {
    ...type.caption,
    fontWeight: weight.semibold,
    color: colors.text,
    textAlign: "center",
  },
});
