import type { Day, Itinerary, Item, PlaceDetail, Trip, UserPlace } from "@detour/shared";
import { type ReactNode, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Cover } from "../components/ds/Cover";
import { KindIcon } from "../components/ds/KindIcon";
import { Icon, type IconName } from "../components/ds/Icon";
import {
  Badge,
  IconButton,
  PlannedFeature,
  SectionTitle,
  StatRow,
} from "../components/ds/primitives";
import { MEAL_LABEL, dayTitle } from "../components/plan/DayPlan";
import {
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Notice,
  ScreenHeader,
  WakingServer,
  useAnnounceOnMount,
} from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useItemActions } from "../data/itemActions";
import { DocumentList } from "../components/documents/DocumentList";
import { placeKey } from "../documents/model";
import { useResource } from "../data/DataProvider";
import { STOP_KIND_LABEL, isEatKind, stopKind } from "../domain/itinerary";
import { useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { formatClock, formatCuisines, formatDate, formatMinutes } from "../util/format";

// One stop of a plan (ADR 021, step 3): what Detour knows about it, and nothing it does not.
// There is no description, rating, price or opening hours in the data (ADR 003, ADR 017,
// CLAUDE.md rule 5), so none is shown; notes, photos, tickets and reservations are planned.

const VENUE_LABEL: Record<string, string> = { restaurant: "Restaurant", cafe: "Café" };

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

/** A hairline row: a small label, the value beside it. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact} accessible accessibilityLabel={`${label}: ${value}.`}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

/** A quiet line with a small icon and no label: when it is, or where. */
function MetaLine({ icon, text }: { icon: IconName; text: string }) {
  return (
    <View style={styles.metaLine} accessible accessibilityLabel={text}>
      <Icon name={icon} size={16} color={colors.muted} />
      <Text style={styles.metaText}>{text}</Text>
    </View>
  );
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
          size="compact"
          testID="edit-display-name"
          onPress={() => setDraft(current)}
        />
        {overridden ? (
          <Button
            label="Use the usual name"
            variant="secondary"
            size="compact"
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
      <Field
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
          size="compact"
          disabled={busy || trimmed.length === 0}
          testID="save-display-name"
          onPress={() => void send(trimmed)}
        />
        <Button
          label="Cancel"
          variant="secondary"
          size="compact"
          disabled={busy}
          onPress={() => setDraft(null)}
        />
      </View>
    </View>
  );
}

function FactCard({ children }: { children: ReactNode }) {
  return <View style={styles.factCard}>{children}</View>;
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
  const trip = trips.data?.find((t) => t.id === tripId);

  if (!plan.data) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Place" onBack={nav.back} />
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
        <ScreenHeader title="Place" onBack={nav.back} />
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
    label: "Typical visit",
    spoken: `Typical visit: ${formatMinutes(item.duration_minutes)}`,
  };
  const address = formatAddress(detail?.address);
  const town = detail?.city_name ?? day.base_city_name ?? null;
  const where =
    [address, address ? null : town].filter(Boolean).join(", ") ||
    (item.lat !== null && item.lon !== null ? formatCoordinates(item.lat, item.lon) : null);
  const venue = item.restaurant?.venue_type ?? detail?.venue_type ?? null;
  const cuisines = item.restaurant?.cuisines ?? detail?.cuisines ?? null;
  const editable = plan.data.profile !== "manual" && trip?.status !== "past" && items.connected;
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
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Cover
          seedKey={item.place_id ?? item.user_place_id ?? item.id}
          photo={item.image}
          height={200}
          creditInset={radius.lg}
        >
          <View style={styles.heroTop}>
            <IconButton icon="back" label="Back" onImage onPress={nav.back} />
          </View>
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
            <KindIcon kind={kind} size={16} />
            <Text style={[styles.kindText, eat && styles.kindTextEat]}>
              {[STOP_KIND_LABEL[kind], town].filter(Boolean).join(" · ")}
            </Text>
          </View>
          {items.problem ? <Notice tone="error">{items.problem}</Notice> : null}
          {tags.length > 0 ? (
            <View style={styles.tagRow}>
              {tags.map((t) => (
                <Badge key={t} label={t} tone="primary" />
              ))}
            </View>
          ) : null}

          <StatRow stats={[dayFigure, lengthFigure]} />
          {where ? (
            <View style={styles.metaBlock}>
              <MetaLine icon="pin" text={where} />
            </View>
          ) : null}

          {meal ? (
            <FactCard>
              {item.meal_type ? <Fact label="Meal" value={MEAL_LABEL[item.meal_type]} /> : null}
              <Fact label="Type" value={venue ? (VENUE_LABEL[venue] ?? venue) : "Not specified"} />
              <Fact label="Cuisine" value={formatCuisines(cuisines)} />
              {detail?.diet_flags && detail.diet_flags.length > 0 ? (
                <Fact
                  label="Diet"
                  value={detail.diet_flags.map((f: string) => f.replace(/_/g, " ")).join(", ")}
                />
              ) : null}
            </FactCard>
          ) : null}

          <View style={styles.actions}>
            <Button
              label="Show on map"
              icon="map"
              variant="secondary"
              size="compact"
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
            {editable && item.type === "visit" ? (
              <>
                <Button
                  label={item.locked ? "Unlock" : "Lock"}
                  icon={item.locked ? "unlock" : "lock"}
                  variant="secondary"
                  size="compact"
                  disabled={items.actions.busyId === item.id}
                  accessibilityLabel={`${item.locked ? "Unlock" : "Lock"} ${item.display_name}`}
                  onPress={() => items.actions.onToggleLock(item)}
                />
                <Button
                  label="Remove"
                  icon="trash"
                  variant="secondary"
                  size="compact"
                  disabled={items.actions.busyId === item.id || item.locked}
                  accessibilityLabel={`Remove ${item.display_name}`}
                  hint={item.locked ? "Unlock it first." : "Shows what would change first."}
                  onPress={() => items.actions.onRemove(item)}
                />
              </>
            ) : null}
          </View>

          {trip ? (
            <View style={styles.section} testID="place-documents">
              <SectionTitle title={eat ? "Bookings and documents" : "Tickets and documents"} />
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
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: { paddingBottom: spacing.xxl },
  heroTop: { paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  kindLine: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  kindText: { ...type.small, fontWeight: "600", color: colors.primary },
  kindTextEat: { color: colors.accentText },
  title: { ...type.display, fontSize: 26, lineHeight: 32, color: colors.text },
  localName: { ...type.small, color: colors.muted, marginTop: spacing.xxs },
  nameNote: { ...type.caption, color: colors.muted, marginTop: spacing.xxs, fontStyle: "italic" },
  nameActions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  nameEditor: { marginTop: spacing.sm },
  // A sheet whose top corners curve over the cover's lower edge, like the trip's tabs.
  body: {
    padding: spacing.lg,
    gap: spacing.lg,
    marginTop: -radius.lg,
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
  },
  tagRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  metaBlock: { gap: spacing.xs },
  metaLine: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  metaText: { ...type.small, color: colors.muted, flex: 1 },
  factCard: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  fact: {
    flexDirection: "row",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  factLabel: { ...type.small, color: colors.muted, width: 72 },
  factValue: { ...type.small, color: colors.text, flex: 1 },
  section: { gap: spacing.xs },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },
  source: { ...type.caption, color: colors.muted },
});
