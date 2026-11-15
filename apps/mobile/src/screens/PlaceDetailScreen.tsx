import type { Day, Itinerary, Item, PlaceDetail, Trip, UserPlace } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Cover } from "../components/ds/Cover";
import { DurationField } from "../components/ds/DurationField";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { parseClock } from "../domain/clock";
import { checkDuration } from "../domain/duration";
import {
  Badge,
  Button,
  CompactHeader,
  CoverBar,
  EmptyState,
  ErrorState,
  InfoRow,
  KindIcon,
  LoadingState,
  MetaLine,
  Notice,
  PlannedFeature,
  SectionHeader,
  StatRow,
  TextField,
  TimeField,
  WakingServer,
  ConfirmSheet,
  ChoiceRow,
  SelectField,
  useAnnounceOnMount,
} from "../components/ds";
import { dayTitle } from "../components/plan/DayPlan";
import { VENUE_LABEL } from "../domain/restaurants";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useItemActions } from "../data/itemActions";
import { DocumentList } from "../components/documents/DocumentList";
import { placeKey } from "../documents/model";
import { useResource } from "../data/DataProvider";
import { STOP_KIND_LABEL, isEatKind, stopKind } from "../domain/itinerary";
import { useNavigation } from "../nav/Navigator";
import { border, colors, layout, radius, spacing, type, weight } from "../theme";
import { formatClock, formatDate, formatDayLabel, formatMinutes } from "../util/format";

// One stop of a plan (ADR 021, step 3): what Detour knows about it, and nothing it does not.
// There is no description, rating, price or opening hours in the data (ADR 003, ADR 017,
// CLAUDE.md rule 5), so none is shown; notes, photos, tickets and reservations are planned.

/** "Hauptstraße 5, 8010 Graz" from the open data's address parts; null when there are none. */
export function formatAddress(address: Record<string, string> | null | undefined): string | null {
  if (!address) return null;
  const street = [address.street, address.housenumber].filter(Boolean).join(" ");
  const town = [address.postcode, address.city].filter(Boolean).join(" ");
  const line = [street, town].filter(Boolean).join(", ");
  return line || null;
}

export function formatCoordinates(lat: number, lon: number): string {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

export function findItem(plan: Itinerary, itemId: string): { day: Day; item: Item } | null {
  for (const day of plan.days) {
    const item = day.items.find((i) => i.id === itemId);
    if (item) return { day, item };
  }
  return null;
}

/** Edit display name (ADR 025): the user's own name for this one place. The original name stays
 * shown beside it, and "Use the usual name" takes the edit back. */
function EditDisplayName({
  placeId,
  current,
  overridden,
  onSaved,
}: {
  placeId: string;
  current: string;
  overridden: boolean;
  onSaved: () => void;
}) {
  const changes = useChangeActions();
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const send = async (name: string | null) => {
    setBusy(true);
    setProblem(null);
    try {
      await changes.setDisplayName(placeId, name);
      setDraft(null);
      onSaved();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  if (draft === null) {
    return (
      <View style={styles.nameActions}>
        <Button
          label="Edit display name"
          icon="note"
          variant="secondary"
          size="sm"
          testID="edit-display-name"
          onPress={() => setDraft(current)}
        />
        {overridden ? (
          <Button
            label="Use the usual name"
            variant="secondary"
            size="sm"
            disabled={busy}
            testID="reset-display-name"
            onPress={() => void send(null)}
          />
        ) : null}
        {problem ? <Notice tone="error">{problem}</Notice> : null}
      </View>
    );
  }
  const trimmed = draft.trim();
  return (
    <View style={styles.nameEditor} testID="display-name-editor">
      <TextField
        label="Display name"
        value={draft}
        onChangeText={setDraft}
        maxLength={120}
        autoFocus
        hint="Only for this place, only on this phone's trips. The local name stays shown."
        error={problem}
      />
      <View style={styles.nameActions}>
        <Button
          label="Save"
          size="sm"
          loading={busy}
          disabled={busy || trimmed.length === 0}
          testID="save-display-name"
          onPress={() => void send(trimmed)}
        />
        <Button
          label="Cancel"
          variant="secondary"
          size="sm"
          disabled={busy}
          onPress={() => setDraft(null)}
        />
      </View>
    </View>
  );
}

/** Edit time: when the user arrives (a typed time or the roulette) and how long they stay (one
 * free field, a pill that goes back to the usual length). A live check says what the new time
 * would run into (the stop before or after, the trip to it, the end of the day). A clash with a
 * neighbouring stop cannot be saved. */
function EditLength({
  day,
  days,
  startDate,
  item,
  itineraryId,
  onSaved,
}: {
  day: Day;
  /** Every day of the plan: the stop can be moved to any of them. */
  days: Day[];
  startDate: string | null;
  item: Item;
  itineraryId: string;
  onSaved: () => void;
}) {
  const changes = useChangeActions();
  const [open, setOpen] = useState(false);
  const [dayIndex, setDayIndex] = useState(day.day_index);
  const [pickingDay, setPickingDay] = useState(false);
  const [minutes, setMinutes] = useState<number | null>(item.duration_minutes);
  const ownStart = formatClock(item.start_time) ?? "";
  const [startText, setStartText] = useState(ownStart);
  const [valid, setValid] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const hasDefault = item.default_duration_minutes != null;
  const effective = minutes ?? item.default_duration_minutes ?? item.duration_minutes;
  const newStart = parseClock(startText);
  // An item with no time may stay without one; otherwise the time must be a time of day.
  const startValid = newStart !== null || (startText.trim() === "" && ownStart === "");
  const startChanged = newStart !== null && newStart !== ownStart;
  const dayChanged = dayIndex !== day.day_index;
  // The day the stop would be on: its clashes are checked there, with the time it would have.
  const target = days.find((d) => d.day_index === dayIndex) ?? day;
  const check =
    valid && startValid
      ? checkDuration(
          target,
          item,
          effective,
          startChanged ? newStart : dayChanged ? (newStart ?? null) : null,
        )
      : null;

  if (!open) {
    return (
      <Button
        label="Edit time"
        icon="clock"
        variant="secondary"
        size="sm"
        testID="edit-length"
        onPress={() => {
          setMinutes(item.duration_minutes);
          setStartText(ownStart);
          setDayIndex(day.day_index);
          setPickingDay(false);
          setValid(true);
          setProblem(null);
          setOpen(true);
        }}
      />
    );
  }
  const lengthUnchanged =
    minutes === null
      ? item.duration_source === "category_default"
      : minutes === item.duration_minutes;
  const unchanged = lengthUnchanged && !startChanged && !dayChanged;
  const save = async () => {
    setBusy(true);
    setProblem(null);
    try {
      // Only what changed is sent. A new start keeps the day in time order.
      const at = startChanged ? newStart : ownStart;
      const position =
        (startChanged || dayChanged) && at
          ? target.items.filter(
              (o) =>
                o.id !== item.id &&
                o.start_time !== null &&
                (formatClock(o.start_time) ?? "") <= at,
            ).length + 1
          : undefined;
      await changes.setSchedule(itineraryId, item.id, {
        ...(lengthUnchanged ? {} : { minutes }),
        ...(startChanged ? { startTime: newStart } : {}),
        ...(dayChanged ? { dayIndex } : {}),
        ...(position !== undefined ? { position } : {}),
      });
      setOpen(false);
      onSaved();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <View style={styles.lengthEditor} testID="length-editor">
      <SelectField
        label="Day"
        placeholder="Choose a day"
        icon="calendar"
        value={formatDayLabel(startDate, dayIndex)}
        open={pickingDay}
        onToggle={() => setPickingDay((o) => !o)}
        testID="edit-day"
      >
        {days.map((d) => (
          <ChoiceRow
            key={d.day_index}
            title={formatDayLabel(startDate, d.day_index)}
            meta={
              d.day_index === day.day_index
                ? "Now here"
                : d.items.length === 0
                  ? "Nothing planned yet"
                  : `${d.items.length} planned`
            }
            selected={dayIndex === d.day_index}
            testID={`edit-day-${d.day_index}`}
            onPress={() => {
              setDayIndex(d.day_index);
              setPickingDay(false);
            }}
          />
        ))}
      </SelectField>
      <TimeField label="Start time" value={startText} onChange={setStartText} testID="edit-start" />
      <DurationField
        label="Length of stay"
        minutes={minutes}
        onChange={setMinutes}
        onValidity={setValid}
        hasDefault={hasDefault}
        defaultMinutes={item.default_duration_minutes ?? null}
      />
      {check ? (
        <Notice
          tone={check.level === "error" ? "error" : "warning"}
          label={check.level === "error" ? "Conflict" : "Check"}
        >
          {check.text}
        </Notice>
      ) : null}
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      <View style={styles.nameActions}>
        <Button
          label="Save"
          size="sm"
          testID="save-length"
          disabled={busy || !valid || !startValid || check?.level === "error" || unchanged}
          loading={busy}
          onPress={() => void save()}
        />
        <Button
          label="Cancel"
          variant="secondary"
          size="sm"
          disabled={busy}
          onPress={() => setOpen(false)}
        />
      </View>
    </View>
  );
}

export function PlaceDetailScreen({
  tripId,
  itineraryId,
  itemId,
}: {
  tripId: string;
  itineraryId: string;
  itemId: string;
}) {
  const nav = useNavigation();
  const insets = useSafeAreaInsets();
  const [stuck, setStuck] = useState(false);
  const titleRef = useAnnounceOnMount();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const plan = useResource<Itinerary>(
    keys.itinerary(itineraryId),
    (c) =>
      call(
        c.GET("/v1/itineraries/{itinerary_id}", {
          params: { path: { itinerary_id: itineraryId } },
        }),
      ),
    { ttlMs: 10 * 60_000 },
  );
  const found = plan.data ? findItem(plan.data, itemId) : null;
  const placeId = found?.item.place_id ?? null;
  const userPlaceId = found?.item.user_place_id ?? null;
  const place = useResource<PlaceDetail>(placeId ? `place:${placeId}` : null, (c) =>
    call(c.GET("/v1/places/{place_id}", { params: { path: { place_id: placeId as string } } })),
  );
  const userPlace = useResource<UserPlace>(userPlaceId ? `user-place:${userPlaceId}` : null, (c) =>
    call(
      c.GET("/v1/user-places/{place_id}", {
        params: { path: { place_id: userPlaceId as string } },
      }),
    ),
  );
  const items = useItemActions(tripId, itineraryId);
  const changes = useChangeActions();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [removeProblem, setRemoveProblem] = useState<string | null>(null);
  const trip = trips.data?.find((t) => t.id === tripId);

  if (!plan.data) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Place" onBack={nav.back} />
        {plan.status === "error" ? (
          <ErrorState text={describeError(plan.error)} onRetry={plan.refresh} />
        ) : plan.waking ? (
          <WakingServer />
        ) : (
          <LoadingState text="Loading the place…" />
        )}
      </View>
    );
  }
  if (!found) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Place" onBack={nav.back} />
        <EmptyState
          title="Not in the plan any more"
          text="This stop was removed or moved when the plan changed."
          action={{ label: "Back", onPress: nav.back }}
        />
      </View>
    );
  }

  const { day, item } = found;
  const kind = stopKind(item);
  const eat = isEatKind(kind);
  const meal = item.type === "meal";
  const detail = place.data;
  const start = formatClock(item.start_time);
  const end = formatClock(item.end_time);
  // The time of day stays on the stop's row in the day list; here the day and the length are
  // two flat figures under the name.
  const timeText = start ? `${start}${end ? ` to ${end}` : ""}` : "time not set";
  const dayFigure = {
    key: "day",
    icon: "calendar" as const,
    value: `Day ${day.day_index}`,
    label: day.date ? formatDate(day.date, false) : "Date not set",
    spoken: `${dayTitle(day)}, ${timeText}`,
  };
  const lengthFigure = {
    key: "length",
    icon: "clock" as const,
    value: formatMinutes(item.duration_minutes),
    label: item.duration_source === "user" ? "Set by you" : "Typical visit",
    spoken: `${item.duration_source === "user" ? "Set by you" : "Typical visit"}: ${formatMinutes(item.duration_minutes)}`,
  };
  const address = formatAddress(detail?.address);
  const town = detail?.city_name ?? day.base_city_name ?? null;
  const where =
    [address, address ? null : town].filter(Boolean).join(", ") ||
    (item.lat !== null && item.lon !== null ? formatCoordinates(item.lat, item.lon) : null);
  const venue = item.restaurant?.venue_type ?? null;
  // A plan made by hand can be locked and edited too; its stops are taken out directly (nothing
  // to recalculate), a generated plan shows a preview first.
  const manual = plan.data.profile === "manual";
  const editable = trip?.status !== "past" && items.connected;
  const removable = manual ? item.type !== "free_time" : item.type === "visit";
  const lengthEditable = trip?.status !== "past" && items.connected && item.type !== "free_time";
  const tags = [
    item.locked ? "Locked" : null,
    item.origin === "user" ? "Added by you" : null,
  ].filter((t): t is string => t !== null);
  const source = detail?.sources?.[0];
  // The English-facing name the server resolved (ADR 025), with the original local name under it;
  // a name Detour romanized itself says so. Older data without names keeps the snapshot.
  const title = item.names?.display ?? item.display_name;
  const localName = item.names
    ? (item.names.local ?? null)
    : detail?.name && detail.name.trim() !== item.display_name.trim()
      ? detail.name
      : null;
  const romanized = item.names?.auto_generated === true;
  const loadingSource =
    (placeId && place.data === undefined && place.status !== "error") ||
    (userPlaceId && userPlace.data === undefined && userPlace.status !== "error");

  return (
    // The cover reaches the very top of the screen, under the status bar, like a trip's cover.
    <View style={[styles.fill, { marginTop: -insets.top }]}>
      <StatusBar style={stuck || !item.image ? "dark" : "light"} />
      <ScrollView
        contentContainerStyle={styles.scroll}
        scrollEventThrottle={32}
        onScroll={(e) => {
          const past = e.nativeEvent.contentOffset.y >= COVER_HEIGHT - radius.xl;
          if (past !== stuck) setStuck(past);
        }}
      >
        <Cover
          seedKey={item.place_id ?? item.user_place_id ?? item.id}
          photo={item.image}
          height={COVER_HEIGHT + insets.top}
          creditInset={radius.xl}
        >
          <CoverBar top={insets.top} onBack={nav.back} />
        </Cover>

        <View style={styles.body}>
          <View ref={titleRef} accessible accessibilityRole="header" accessibilityLabel={title}>
            <Text style={styles.title}>{title}</Text>
            {localName ? (
              <Text style={styles.localName} accessibilityLabel={`Local name: ${localName}`}>
                {localName}
              </Text>
            ) : null}
            {romanized ? (
              <Text style={styles.nameNote} testID="name-romanized">
                Automatically romanized
              </Text>
            ) : null}
          </View>
          {placeId && trip?.status !== "past" && items.connected ? (
            <EditDisplayName
              placeId={placeId}
              current={title}
              overridden={item.names?.user_override === true}
              onSaved={() => {
                plan.refresh();
                place.refresh();
              }}
            />
          ) : null}
          <View
            style={styles.kindLine}
            accessible
            accessibilityLabel={[STOP_KIND_LABEL[kind], town].filter(Boolean).join(", ")}
          >
            <KindIcon kind={kind} size="sm" />
            <Text style={[styles.kindText, eat && styles.kindTextEat]}>
              {[STOP_KIND_LABEL[kind], town].filter(Boolean).join(" · ")}
            </Text>
          </View>
          {items.problem || removeProblem ? (
            <Notice tone="error">{items.problem ?? removeProblem}</Notice>
          ) : null}
          {tags.length > 0 ? (
            <View style={styles.tagRow}>
              {tags.map((t) => (
                <Badge key={t} label={t} tone="primary" />
              ))}
            </View>
          ) : null}

          <StatRow stats={[dayFigure, lengthFigure]} />
          {where ? <MetaLine icon="pin" text={where} /> : null}
          {meal ? (
            <InfoRow label="Type" value={venue ? VENUE_LABEL[venue] : "Not specified"} />
          ) : null}

          <View style={styles.actions}>
            <Button
              label="Show on map"
              icon="map"
              variant="secondary"
              size="sm"
              testID="show-on-map"
              onPress={() =>
                nav.push({
                  name: "itinerary",
                  tripId,
                  itineraryId,
                  view: "map",
                  day: day.day_index,
                  itemId: item.id,
                })
              }
            />
            {lengthEditable ? (
              <EditLength
                key={`${item.id}:${item.duration_minutes}:${day.day_index}`}
                day={day}
                days={plan.data.days}
                startDate={trip?.start_date ?? null}
                item={item}
                itineraryId={itineraryId}
                onSaved={plan.refresh}
              />
            ) : null}
            {editable && removable ? (
              <>
                <Button
                  label={item.locked ? "Unlock" : "Lock"}
                  icon={item.locked ? "unlock" : "lock"}
                  variant="secondary"
                  size="sm"
                  disabled={items.actions.busyId === item.id}
                  accessibilityLabel={`${item.locked ? "Unlock" : "Lock"} ${item.display_name}`}
                  onPress={() => items.actions.onToggleLock(item)}
                />
                <Button
                  label="Remove"
                  icon="trash"
                  variant="secondary"
                  tone="danger"
                  size="sm"
                  disabled={items.actions.busyId === item.id || item.locked}
                  accessibilityLabel={`Remove ${item.display_name}`}
                  hint={
                    item.locked
                      ? "Unlock it first."
                      : manual
                        ? "Asks first."
                        : "Shows what would change first."
                  }
                  onPress={() => (manual ? setConfirmRemove(true) : items.actions.onRemove(item))}
                />
              </>
            ) : null}
          </View>

          {trip ? (
            <View style={styles.section} testID="place-documents">
              <SectionHeader title={eat ? "Bookings and documents" : "Tickets and documents"} />
              <DocumentList
                trip={trip}
                filter={(link) => link.kind === "place" && link.key === placeKey(item)}
                addLink={{
                  kind: "place",
                  key: placeKey(item),
                  name: item.display_name,
                  day: day.day_index,
                }}
              />
            </View>
          ) : null}

          <PlannedFeature
            icon="note"
            title={eat ? "Notes, photos and reservations" : "Notes and photos"}
            text={
              eat
                ? "Your notes, photos and reservation details for this place will be kept here. Not built yet."
                : "Your notes and photos of this place will be kept here. Not built yet."
            }
            testID="place-planned"
          />

          {userPlaceId || source || loadingSource ? (
            <Text style={styles.source} testID="place-source">
              {userPlaceId
                ? "A place you added."
                : source
                  ? `Data: ${source.attribution} (${source.licence}).`
                  : "Loading the data source…"}
            </Text>
          ) : null}
        </View>
      </ScrollView>
      <ConfirmSheet
        visible={confirmRemove}
        title={`Remove ${item.display_name}?`}
        message="It is taken off this day. You can add it again later."
        confirmLabel="Yes, remove it"
        cancelLabel="Keep it"
        busy={removing}
        confirmTestID="confirm-remove"
        onCancel={() => setConfirmRemove(false)}
        onConfirm={() => {
          setRemoving(true);
          setRemoveProblem(null);
          changes
            .removeItem(tripId, itineraryId, item.id)
            .then(() => nav.back())
            .catch((e: unknown) => setRemoveProblem(describeError(e)))
            .finally(() => {
              setRemoving(false);
              setConfirmRemove(false);
            });
        }}
      />
    </View>
  );
}

const COVER_HEIGHT = 200;

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { paddingBottom: spacing.xxl },
  kindLine: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  kindText: { ...type.label, fontWeight: weight.semibold, color: colors.primary },
  kindTextEat: { color: colors.accentText },
  title: { ...type.hero, color: colors.text },
  localName: { ...type.label, color: colors.muted, marginTop: spacing.xxs },
  nameNote: { ...type.caption, color: colors.muted, marginTop: spacing.xxs, fontStyle: "italic" },
  nameActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  nameEditor: { marginTop: spacing.sm },
  lengthEditor: { alignSelf: "stretch", width: "100%", gap: spacing.sm },
  // A sheet whose top corners curve over the cover's lower edge, like the trip's tabs.
  body: {
    paddingHorizontal: layout.gutter,
    paddingTop: layout.section,
    gap: layout.block,
    marginTop: -radius.xl,
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  tagRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  section: {
    gap: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: border.hairline,
    borderTopColor: colors.border,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },
  source: { ...type.caption, color: colors.muted },
});
