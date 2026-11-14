import type { Trip } from "@detour/shared";
import { type ReactNode, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { call } from "../api/unwrap";
import { Button } from "../components/Button";
import { DEVICE_ONLY_NOTE, KindTile } from "../components/documents/DocumentList";
import { CalendarSheet } from "../components/ds/Calendar";
import { Icon } from "../components/ds/Icon";
import { IconButton, ListRow, RowGroup } from "../components/ds/primitives";
import { Chip, EmptyState, Field, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useActivePlan } from "../data/tripCounts";
import { useDocument, useDocumentActions } from "../documents/DocumentsProvider";
import {
  CATEGORIES,
  CATEGORY_LABEL,
  NOTES_MAX,
  type DocCategory,
  type DocLink,
  type PickedFile,
  type TripDocument,
  fileLine,
  isAccepted,
  linkableLegs,
  linkablePlaces,
  titleFromFileName,
} from "../documents/model";
import { useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { localToday, shortSpan } from "../domain/trips";
import { formatDate, formatDayLabel } from "../util/format";

type LinkKind = DocLink["kind"];

const LINK_KIND_LABEL: Record<LinkKind, string> = {
  trip: "Whole trip",
  day: "A day",
  place: "A place",
  leg: "A journey",
};

/**
 * Add a document to a trip, or edit one (ADR 023). The file is picked with the system picker
 * (PDFs and pictures), then given a title, a kind and what it is about. The file is copied into
 * the app's own storage on this phone; nothing is uploaded.
 */
export function DocumentFormScreen({
  tripId,
  documentId,
  link,
  category,
}: {
  tripId: string;
  documentId?: string;
  link?: DocLink;
  category?: DocCategory;
}) {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const existing = useDocument(documentId);

  if (trips.data === undefined || (documentId && existing === undefined)) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title={documentId ? "Edit document" : "Add a document"} onBack={nav.back} />
        <LoadingState text="Loading…" />
      </View>
    );
  }
  if (!trip || (documentId && !existing)) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title={documentId ? "Edit document" : "Add a document"} onBack={nav.back} />
        <EmptyState
          title={trip ? "Document not found" : "Trip not found"}
          text="It may have been deleted."
          action={{ label: "Back", onPress: nav.back }}
        />
      </View>
    );
  }
  return (
    <Form trip={trip} existing={existing ?? null} initialLink={link} initialCategory={category} />
  );
}

function Form({
  trip,
  existing,
  initialLink,
  initialCategory,
}: {
  trip: Trip;
  existing: TripDocument | null;
  initialLink?: DocLink;
  initialCategory?: DocCategory;
}) {
  const nav = useNavigation();
  const actions = useDocumentActions();
  const plan = useActivePlan(trip);
  const days = plan.data?.days ?? [];
  const places = linkablePlaces(days);
  const legs = linkableLegs(days);
  const dayCount = days.length || trip.duration_days;

  const start = existing?.link ?? initialLink ?? { kind: "trip" as const };
  const [picked, setPicked] = useState<PickedFile | null>(null);
  const [title, setTitle] = useState(existing?.title ?? "");
  const [category, setCategory] = useState<DocCategory | null>(
    existing?.category ?? initialCategory ?? null,
  );
  const [date, setDate] = useState(existing?.date ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [calendar, setCalendar] = useState(false);
  const [kind, setKind] = useState<LinkKind>(start.kind);
  const [day, setDay] = useState<number | null>(start.kind === "day" ? start.day : null);
  const [place, setPlace] = useState<{ key: string; name: string; day: number | null } | null>(
    start.kind === "place" ? { key: start.key, name: start.name, day: start.day } : null,
  );
  const [leg, setLeg] = useState<{ day: number; name: string } | null>(
    start.kind === "leg" ? { day: start.day, name: start.name } : null,
  );
  const [busy, setBusy] = useState<"pick" | "save" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  // A place or journey already linked stays choosable even if the plan no longer has it.
  const placeOptions =
    place && !places.some((p) => p.key === place.key)
      ? [{ key: place.key, name: place.name, day: place.day ?? 0 }, ...places]
      : places;
  const legOptions =
    leg && !legs.some((l) => l.day === leg.day) ? [{ ...leg, from: null }, ...legs] : legs;
  const kinds: LinkKind[] = [
    "trip",
    "day",
    ...(placeOptions.length ? (["place"] as const) : []),
    ...(legOptions.length ? (["leg"] as const) : []),
  ];

  const chosenLink: DocLink | null =
    kind === "trip"
      ? { kind: "trip" }
      : kind === "day"
        ? day
          ? { kind: "day", day }
          : null
        : kind === "place"
          ? place
            ? { kind: "place", key: place.key, name: place.name, day: place.day || null }
            : null
          : leg
            ? { kind: "leg", day: leg.day, name: leg.name }
            : null;
  const ready =
    (existing !== null || picked !== null) &&
    title.trim().length > 0 &&
    category !== null &&
    chosenLink !== null &&
    busy === null;

  const pick = async () => {
    setBusy("pick");
    setProblem(null);
    try {
      const file = await actions.pick();
      if (!file) return; // cancelled
      if (!isAccepted(file.mimeType)) {
        setProblem("Detour keeps PDFs and pictures. Choose a PDF or an image file.");
        return;
      }
      setPicked(file);
      if (!title.trim()) setTitle(titleFromFileName(file.name));
    } catch {
      setProblem("The file could not be read. Try again, or choose another file.");
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (!category || !chosenLink) return;
    setBusy("save");
    setProblem(null);
    const fields = { title, category, link: chosenLink, date: date || null, notes };
    try {
      if (existing) {
        await actions.update(existing, fields);
        nav.back();
      } else if (picked) {
        const doc = await actions.add(trip.id, picked, fields);
        nav.replace({ name: "document", tripId: trip.id, documentId: doc.id });
      }
    } catch {
      setProblem(
        "The document could not be saved on this phone. Check the free space and try again.",
      );
      setBusy(null);
    }
  };

  // Step one (reference screen 16, left): how to add. Only the phone's file picker is built; it
  // also reaches Google Drive, because Android's picker lists it.
  if (!existing && !picked) {
    return (
      <View style={styles.fill}>
        <ScrollView contentContainerStyle={styles.content}>
          <ScreenHeader
            title="Add document"
            subtitle={`${trip.title} · ${shortSpan(trip)}`}
            onBack={nav.back}
          />
          <View style={styles.body}>
            {problem ? <Notice tone="error">{problem}</Notice> : null}
            <Text style={styles.lead}>
              Keep your tickets, bookings and other travel documents in one place.
            </Text>
            <RowGroup>
              <ListRow
                icon="export"
                title="Upload from device"
                detail="Add a PDF or a picture from your phone, or from Google Drive through the phone's file picker."
                testID="choose-file"
                onPress={() => void pick()}
              />
              <ListRow
                icon="photos"
                title="Take a photo"
                detail="Scan a ticket, reservation or document with the camera."
                disabled
                testID="take-photo"
              />
              <ListRow
                icon="route"
                title="Add a link"
                detail="A link to a ticket, a booking or a confirmation email."
                disabled
                testID="add-link"
              />
            </RowGroup>
            <View style={styles.or}>
              <View style={styles.orLine} />
              <Text style={styles.orText}>or create manually</Text>
              <View style={styles.orLine} />
            </View>
            <RowGroup>
              <ListRow
                icon="document"
                title="Create a document"
                detail="A name, a kind and notes; you add the file later."
                disabled
                testID="create-document"
              />
            </RowGroup>
            {busy === "pick" ? <Text style={styles.muted}>Opening the file picker…</Text> : null}
            <View style={styles.privacy}>
              <Icon name="shield" size={22} color={colors.primary} />
              <View style={styles.fileText}>
                <Text style={styles.privacyTitle}>Your documents stay private</Text>
                <Text style={styles.muted}>{DEVICE_ONLY_NOTE}</Text>
              </View>
            </View>
          </View>
        </ScrollView>
      </View>
    );
  }

  const fileName = existing?.fileName ?? (picked as PickedFile).name;
  const fileText = existing
    ? fileLine(existing)
    : fileLine({ ...(picked as PickedFile), sizeBytes: picked?.size ?? null });
  const fileUri = existing?.uri ?? picked?.uri ?? null;
  const fileIsImage = (existing?.mimeType ?? picked?.mimeType ?? "").startsWith("image/");

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <ScreenHeader
          title={existing ? "Edit document" : "Add document"}
          subtitle={`${trip.title} · ${shortSpan(trip)}`}
          onBack={nav.back}
        />
        <View style={styles.body}>
          {problem ? <Notice tone="error">{problem}</Notice> : null}

          <FileRow
            name={fileName}
            line={fileText}
            uri={fileIsImage ? fileUri : null}
            category={category ?? "other"}
            action={
              existing ? null : (
                <Button
                  label="Replace file"
                  variant="secondary"
                  testID="replace-file"
                  loading={busy === "pick"}
                  onPress={() => void pick()}
                />
              )
            }
          />

          <View style={styles.gap}>
            <Text style={styles.label}>Document type</Text>
            <View style={styles.row}>
              {CATEGORIES.map((c) => (
                <Chip
                  key={c}
                  label={CATEGORY_LABEL[c]}
                  selected={category === c}
                  onPress={() => setCategory(c)}
                />
              ))}
            </View>
          </View>

          <Field
            label="Title"
            value={title}
            onChangeText={setTitle}
            maxLength={80}
            hint="For example “Train to Salzburg” or “Travel insurance”."
          />

          <View style={styles.gap}>
            <Text style={styles.label}>
              Related to <Text style={styles.optional}>(optional)</Text>
            </Text>
            <View style={styles.row}>
              {kinds.map((k) => (
                <Chip
                  key={k}
                  label={LINK_KIND_LABEL[k]}
                  selected={kind === k}
                  testID={`link-${k}`}
                  onPress={() => setKind(k)}
                />
              ))}
            </View>
            {kind === "day" ? (
              <View style={styles.row}>
                {Array.from({ length: dayCount }, (_, i) => i + 1).map((d) => (
                  <Chip
                    key={d}
                    label={formatDayLabel(trip.start_date, d)}
                    selected={day === d}
                    onPress={() => setDay(d)}
                  />
                ))}
              </View>
            ) : null}
            {kind === "place"
              ? placeOptions.map((p) => (
                  <ChoiceRow
                    key={p.key}
                    title={p.name}
                    meta={p.day ? `Day ${p.day}` : "No longer in the plan"}
                    selected={place?.key === p.key}
                    onPress={() => setPlace({ key: p.key, name: p.name, day: p.day || null })}
                  />
                ))
              : null}
            {kind === "leg"
              ? legOptions.map((l) => (
                  <ChoiceRow
                    key={l.day}
                    title={`To ${l.name}`}
                    meta={`Day ${l.day}${l.from ? ` · from ${l.from}` : ""}`}
                    selected={leg?.day === l.day}
                    onPress={() => setLeg({ day: l.day, name: l.name })}
                  />
                ))
              : null}
          </View>

          <View style={styles.gap}>
            <Text style={styles.label}>
              Date <Text style={styles.optional}>(optional)</Text>
            </Text>
            <View style={styles.dateRow}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={date ? `Date, ${formatDate(date)}` : "Date, not set"}
                accessibilityHint="Opens a calendar"
                onPress={() => setCalendar(true)}
                style={styles.dateField}
                testID="document-date"
              >
                <Icon name="calendar" size={22} color={colors.text} />
                <Text style={[styles.dateText, !date && styles.placeholder]}>
                  {date ? formatDate(date) : "Choose a date"}
                </Text>
              </Pressable>
              {date ? (
                <IconButton
                  icon="close"
                  label="Clear the date"
                  testID="clear-document-date"
                  onPress={() => setDate("")}
                />
              ) : null}
            </View>
          </View>
          <CalendarSheet
            visible={calendar}
            title="Date of the document"
            value={date}
            today={localToday()}
            onPick={(iso) => {
              setDate(iso);
              setCalendar(false);
            }}
            onClear={() => {
              setDate("");
              setCalendar(false);
            }}
            onClose={() => setCalendar(false)}
          />

          <View style={styles.gap}>
            <Text style={styles.label}>
              Notes <Text style={styles.optional}>(optional)</Text>
            </Text>
            <TextInput
              accessibilityLabel="Notes (optional)"
              value={notes}
              onChangeText={setNotes}
              maxLength={NOTES_MAX}
              multiline
              textAlignVertical="top"
              placeholder="For example: outbound flight, confirmation email from the airline"
              placeholderTextColor={colors.muted}
              style={styles.notes}
              testID="document-notes"
            />
            <Text
              style={styles.counter}
              accessibilityLabel={`${notes.length} of ${NOTES_MAX} characters`}
            >
              {notes.length}/{NOTES_MAX}
            </Text>
          </View>

          <Button
            label="Save document"
            variant="ink"
            fill
            testID="save-document"
            disabled={!ready}
            loading={busy === "save"}
            onPress={() => void save()}
          />
          {!existing ? <Text style={styles.note}>{DEVICE_ONLY_NOTE}</Text> : null}
        </View>
      </ScrollView>
    </View>
  );
}

function FileRow({
  name,
  line,
  uri,
  category,
  action,
}: {
  name: string;
  line: string;
  /** The picture itself, for an image; a PDF shows its kind's tile. */
  uri: string | null;
  category: DocCategory;
  action: ReactNode;
}) {
  return (
    <View style={styles.file}>
      <View accessible accessibilityLabel={`File: ${name}. ${line}`} style={styles.fileHead}>
        {uri ? (
          <Image
            source={{ uri }}
            style={styles.filePicture}
            resizeMode="cover"
            accessibilityIgnoresInvertColors
            testID="file-picture"
          />
        ) : (
          <KindTile category={category} size={64} />
        )}
        <View style={styles.fileText}>
          <Text style={styles.fileName} numberOfLines={2}>
            {name}
          </Text>
          <Text style={styles.muted}>{line}</Text>
        </View>
      </View>
      {action}
    </View>
  );
}

function ChoiceRow({
  title,
  meta,
  selected,
  onPress,
}: {
  title: string;
  meta: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}, ${meta}`}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <View style={styles.fileText}>
        <Text style={styles.fileName}>
          {selected ? "✓ " : ""}
          {title}
        </Text>
        <Text style={styles.muted}>{meta}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  body: { paddingHorizontal: spacing.lg, gap: spacing.xl },
  gap: { gap: spacing.sm },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  label: { ...type.small, fontWeight: "700", color: colors.text },
  muted: { ...type.small, color: colors.muted },
  note: { ...type.caption, color: colors.muted },
  lead: { ...type.body, color: colors.muted },
  optional: { fontWeight: "400", color: colors.muted },
  or: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  orLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  orText: { ...type.small, color: colors.muted },
  privacy: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
  },
  privacyTitle: { ...type.small, fontWeight: "700", color: colors.text },
  file: {
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  fileHead: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  filePicture: {
    width: 64,
    height: 64,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
  },
  dateRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  dateField: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: TOUCH,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.outline,
  },
  dateText: { ...type.body, color: colors.text },
  placeholder: { color: colors.muted },
  notes: {
    ...type.body,
    color: colors.text,
    minHeight: 96,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.outline,
    borderRadius: radius.md,
  },
  counter: { ...type.caption, color: colors.muted, textAlign: "right" },
  fileText: { flex: 1, gap: spacing.xxs },
  fileName: { ...type.body, fontWeight: "600", color: colors.text },
  choice: {
    minHeight: TOUCH,
    justifyContent: "center",
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  choiceSelected: { backgroundColor: colors.surfaceMuted },
});
