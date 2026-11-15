import type { Trip } from "@detour/shared";
import { type ReactNode, useState } from "react";
import { Image, StyleSheet, Text, View } from "react-native";

import { call } from "../api/unwrap";
import { CATEGORY_ICON, DEVICE_ONLY_NOTE, KindTile } from "../components/documents/DocumentList";
import { CalendarSheet } from "../components/ds/Calendar";
import {
  Button,
  Card,
  ChoiceRow,
  Chip,
  EmptyState,
  FieldShell,
  type IconName,
  InlineStatus,
  ListRow,
  LoadingState,
  Notice,
  ScreenHeader,
  SelectField,
  TextField,
  Tile,
  KeyboardScrollView,
} from "../components/ds";
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
import { colors, docTones, layout, radius, size as sizes, spacing, type, weight } from "../theme";
import { localToday, shortSpan } from "../domain/trips";
import { formatDate, formatDayLabel } from "../util/format";

type LinkKind = DocLink["kind"];

const LINK_KIND_LABEL: Record<LinkKind, string> = {
  trip: "Whole trip",
  day: "A day",
  place: "Attraction",
  leg: "A journey",
};

const LINK_KIND_ICON: Record<LinkKind, IconName> = {
  trip: "trips",
  day: "calendar",
  place: "pin",
  leg: "route",
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
  // Whole trip or an attraction. A document saved earlier about a day or a journey keeps its link
  // and its chip, so editing it never loses what it was about.
  const kinds: LinkKind[] = [
    "trip",
    ...(placeOptions.length ? (["place"] as const) : []),
    ...(start.kind === "day" || start.kind === "leg" ? [start.kind] : []),
  ];
  const [picking, setPicking] = useState(false);

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

  // Step one (reference screen 16, left): how to add, as cards. Only the phone's file picker is
  // built; it also reaches Google Drive, because Android's picker lists it.
  if (!existing && !picked) {
    return (
      <View style={styles.fill}>
        <KeyboardScrollView contentContainerStyle={styles.content}>
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
            <View style={styles.cards}>
              <OptionCard
                icon="export"
                tone="ticket"
                title="Upload from device"
                detail="A PDF or a picture from your phone, or from Google Drive through the phone's file picker."
                testID="choose-file"
                onPress={() => void pick()}
              />
              <OptionCard
                icon="photos"
                tone="transport"
                title="Take a photo"
                detail="Scan a ticket, reservation or document with the camera."
                disabled
                testID="take-photo"
              />
            </View>
            {busy === "pick" ? <InlineStatus text="Opening the file picker…" busy /> : null}
            <ListRow
              icon="shield"
              title="Your documents stay private"
              detail={DEVICE_ONLY_NOTE}
              density="compact"
              inset="none"
              divider={false}
            />
          </View>
        </KeyboardScrollView>
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
      <KeyboardScrollView contentContainerStyle={styles.content}>
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
                  icon="refresh"
                  variant="secondary"
                  size="sm"
                  testID="replace-file"
                  loading={busy === "pick"}
                  onPress={() => void pick()}
                />
              )
            }
          />

          <FieldShell label="Document type">
            <View style={styles.row}>
              {CATEGORIES.map((c) => (
                <Chip
                  key={c}
                  label={CATEGORY_LABEL[c]}
                  icon={CATEGORY_ICON[c]}
                  selected={category === c}
                  onPress={() => setCategory(c)}
                />
              ))}
            </View>
          </FieldShell>

          <TextField
            label="Title"
            accessibilityLabel="Title"
            accessibilityHint="For example “Train to Salzburg” or “Museum tickets”."
            value={title}
            onChangeText={setTitle}
            maxLength={80}
            placeholder="For example “Train to Salzburg”"
            onClear={() => setTitle("")}
            clearLabel="Clear the title"
          />

          <FieldShell label="Related to (optional)">
            <View style={styles.row}>
              {kinds.map((k) => (
                <Chip
                  key={k}
                  label={LINK_KIND_LABEL[k]}
                  icon={LINK_KIND_ICON[k]}
                  selected={kind === k}
                  testID={`link-${k}`}
                  onPress={() => {
                    setKind(k);
                    setPicking(false);
                  }}
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
            {kind === "place" ? (
              <SelectField
                label="Attraction"
                placeholder="Choose an attraction"
                value={place?.name ?? null}
                open={picking}
                onToggle={() => setPicking((o) => !o)}
                testID="attraction-select"
              >
                {placeOptions.map((p) => (
                  <ChoiceRow
                    key={p.key}
                    title={p.name}
                    meta={p.day ? `Day ${p.day}` : "No longer in the plan"}
                    selected={place?.key === p.key}
                    onPress={() => {
                      setPlace({ key: p.key, name: p.name, day: p.day || null });
                      setPicking(false);
                    }}
                  />
                ))}
              </SelectField>
            ) : null}
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
          </FieldShell>

          <SelectField
            label="Date (optional)"
            placeholder="Choose a date"
            icon="calendar"
            value={date ? formatDate(date) : null}
            accessibilityLabel={date ? `Date, ${formatDate(date)}` : "Date, not set"}
            accessibilityHint="Opens a calendar"
            onPress={() => setCalendar(true)}
            onClear={() => setDate("")}
            clearLabel="Clear the date"
            testID="document-date"
          />
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

          <TextField
            label="Notes (optional)"
            accessibilityLabel="Notes (optional)"
            value={notes}
            onChangeText={setNotes}
            maxLength={NOTES_MAX}
            multiline
            placeholder="For example: outbound flight, confirmation email from the airline"
            hint={`${notes.length}/${NOTES_MAX} characters`}
            testID="document-notes"
          />

          <Button
            label="Save document"
            fill
            testID="save-document"
            disabled={!ready}
            loading={busy === "save"}
            onPress={() => void save()}
          />
          {!existing ? <Text style={styles.note}>{DEVICE_ONLY_NOTE}</Text> : null}
        </View>
      </KeyboardScrollView>
    </View>
  );
}

/** A way to add, as a card: a tinted tile, a title, a line and a chevron. Disabled says why. */
function OptionCard({
  icon,
  tone,
  title,
  detail,
  disabled = false,
  onPress,
  testID,
}: {
  icon: IconName;
  tone: DocCategory;
  title: string;
  detail: string;
  disabled?: boolean;
  onPress?: () => void;
  testID?: string;
}) {
  const colour = docTones[tone];
  return (
    <Card padded={false}>
      <ListRow
        leading={<Tile icon={icon} fg={colour.fg} bg={colour.bg} />}
        title={title}
        detail={detail}
        disabled={disabled}
        onPress={onPress}
        inset="panel"
        divider={false}
        accessibilityLabel={`${title}. ${detail}${disabled ? " Coming later." : ""}`}
        testID={testID}
      />
    </Card>
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
    <Card>
      <View style={styles.file}>
        {uri ? (
          <Image
            source={{ uri }}
            style={styles.filePicture}
            resizeMode="cover"
            accessibilityIgnoresInvertColors
            testID="file-picture"
          />
        ) : (
          <KindTile category={category} size="lg" />
        )}
        <View style={styles.fileText}>
          <View accessible accessibilityLabel={`File: ${name}. ${line}`}>
            <Text style={styles.fileName} numberOfLines={2}>
              {name}
            </Text>
            <Text style={styles.muted}>{line}</Text>
          </View>
          {action}
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  body: { paddingHorizontal: layout.gutter, gap: layout.section },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  muted: { ...type.caption, color: colors.muted },
  note: { ...type.caption, color: colors.muted, textAlign: "center" },
  lead: { ...type.label, color: colors.muted },
  cards: { gap: spacing.sm },
  file: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  filePicture: {
    width: sizes.thumb,
    height: sizes.thumb,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
  },
  fileText: { flex: 1, gap: spacing.xs },
  fileName: { ...type.label, fontWeight: weight.semibold, color: colors.text },
});
