import type { Trip } from "@detour/shared";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { call } from "../api/unwrap";
import { Button } from "../components/Button";
import { CATEGORY_ICON, DEVICE_ONLY_NOTE } from "../components/documents/DocumentList";
import { Icon } from "../components/ds/Icon";
import { Chip, EmptyState, Field, LoadingState, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useActivePlan } from "../data/tripCounts";
import { useDocument, useDocumentActions } from "../documents/DocumentsProvider";
import {
  CATEGORIES,
  CATEGORY_LABEL,
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
import { TOUCH, colors, spacing, type } from "../theme";
import { formatDayLabel } from "../util/format";

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
}: {
  tripId: string;
  documentId?: string;
  link?: DocLink;
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
  return <Form trip={trip} existing={existing ?? null} initialLink={link} />;
}

function Form({
  trip,
  existing,
  initialLink,
}: {
  trip: Trip;
  existing: TripDocument | null;
  initialLink?: DocLink;
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
  const [category, setCategory] = useState<DocCategory | null>(existing?.category ?? null);
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
    const fields = { title, category, link: chosenLink };
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

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <ScreenHeader
          title={existing ? "Edit document" : "Add a document"}
          subtitle={trip.title}
          onBack={nav.back}
        />
        <View style={styles.body}>
          {problem ? <Notice tone="error">{problem}</Notice> : null}

          {existing ? (
            <FileRow name={existing.fileName} line={fileLine(existing)} />
          ) : picked ? (
            <View style={styles.gap}>
              <FileRow name={picked.name} line={fileLine({ ...picked, sizeBytes: picked.size })} />
              <Button label="Choose another file" variant="quiet" onPress={() => void pick()} />
            </View>
          ) : (
            <View style={styles.gap}>
              <Button
                label="Choose a file"
                icon="document"
                variant="secondary"
                testID="choose-file"
                loading={busy === "pick"}
                hint="Opens the phone's file picker: a PDF or a picture"
                onPress={() => void pick()}
              />
              <Text style={styles.muted}>A PDF or a picture: a ticket, a booking, a policy.</Text>
            </View>
          )}

          <Field
            label="Title"
            value={title}
            onChangeText={setTitle}
            maxLength={80}
            hint="For example “Train to Salzburg” or “Travel insurance”."
          />

          <View style={styles.gap}>
            <Text style={styles.label}>Kind</Text>
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

          <View style={styles.gap}>
            <Text style={styles.label}>About</Text>
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

          <Button
            label={existing ? "Save" : "Add the document"}
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

function FileRow({ name, line }: { name: string; line: string }) {
  return (
    <View style={styles.file} accessible accessibilityLabel={`File: ${name}. ${line}`}>
      <Icon name={CATEGORY_ICON.other} color={colors.primary} />
      <View style={styles.fileText}>
        <Text style={styles.fileName} numberOfLines={1}>
          {name}
        </Text>
        <Text style={styles.muted}>{line}</Text>
      </View>
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
  file: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
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
