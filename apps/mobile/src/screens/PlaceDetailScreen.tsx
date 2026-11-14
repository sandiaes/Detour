import type { Day, Itinerary, Item, PlaceDetail, Trip, UserPlace } from "@detour/shared";
import type { ReactNode } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Cover, PhotoCredit } from "../components/ds/Cover";
import { Icon, type IconName } from "../components/ds/Icon";
import { Badge, IconButton, PlannedFeature, SectionTitle } from "../components/ds/primitives";
import { MEAL_LABEL, dayTitle } from "../components/plan/DayPlan";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  ScreenHeader,
  WakingServer,
  useAnnounceOnMount,
} from "../components/ui";
import { keys } from "../data/actions";
import { useItemActions } from "../data/itemActions";
import { useResource } from "../data/DataProvider";
import { STOP_KIND_LABEL, isEatKind, stopKind } from "../domain/itinerary";
import { useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { formatClock, formatCuisines, formatMinutes } from "../util/format";

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

function Fact({
  icon,
  label,
  value,
  note,
}: {
  icon: IconName;
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <View
      style={styles.fact}
      accessible
      accessibilityLabel={`${label}: ${value}.${note ? ` ${note}` : ""}`}
    >
      <View style={styles.factIcon}>
        <Icon name={icon} size={18} color={colors.primary} />
      </View>
      <View style={styles.factText}>
        <Text style={styles.factLabel}>{label}</Text>
        <Text style={styles.factValue}>{value}</Text>
        {note ? <Text style={styles.factNote}>{note}</Text> : null}
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
  const when = `${dayTitle(day)}${start ? `, ${start}${end ? ` to ${end}` : ""}` : ", time not set"}`;
  const duration = `${formatMinutes(item.duration_minutes)} (${
    item.duration_source === "user"
      ? "set by you"
      : meal
        ? "typical meal length"
        : "typical visit length"
  })`;
  const address = formatAddress(detail?.address);
  const town = detail?.city_name ?? day.base_city_name ?? null;
  const where =
    [address, address ? null : town].filter(Boolean).join(", ") ||
    (item.lat !== null && item.lon !== null ? formatCoordinates(item.lat, item.lon) : "Not known");
  const venue = item.restaurant?.venue_type ?? detail?.venue_type ?? null;
  const cuisines = item.restaurant?.cuisines ?? detail?.cuisines ?? null;
  const editable = plan.data.profile !== "manual" && trip?.status !== "past" && items.connected;
  const tags = [
    item.locked ? "Locked" : null,
    item.origin === "user" ? "Added by you" : null,
  ].filter((t): t is string => t !== null);
  const source = detail?.sources?.[0];
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
        >
          <View style={styles.heroTop}>
            <IconButton icon="back" label="Back" onImage onPress={nav.back} />
          </View>
          <View style={styles.heroText}>
            <Badge label={STOP_KIND_LABEL[kind]} tone={eat ? "accent" : "primary"} />
            <View
              ref={titleRef}
              accessible
              accessibilityRole="header"
              accessibilityLabel={item.display_name}
            >
              <Text style={styles.heroTitle} numberOfLines={2}>
                {item.display_name}
              </Text>
            </View>
          </View>
        </Cover>

        <View style={styles.body}>
          <PhotoCredit photo={item.image} />
          {items.problem ? <Notice tone="error">{items.problem}</Notice> : null}
          {tags.length > 0 ? (
            <View style={styles.tagRow}>
              {tags.map((t) => (
                <Badge key={t} label={t} tone="primary" />
              ))}
            </View>
          ) : null}

          <FactCard>
            <Fact icon="calendar" label="When" value={when} />
            <Fact icon="clock" label="Duration" value={duration} />
            <Fact
              icon="pin"
              label="Location"
              value={where}
              note={address && town ? town : undefined}
            />
            {!meal ? (
              <Fact
                icon="clock"
                label="Opening hours"
                value="Not checked"
                note="Detour has no opening hours for this place. Check them before you go."
              />
            ) : null}
          </FactCard>

          {meal ? (
            <FactCard>
              {item.meal_type ? (
                <Fact icon="restaurant" label="Meal" value={MEAL_LABEL[item.meal_type]} />
              ) : null}
              <Fact
                icon="restaurant"
                label="Type"
                value={venue ? (VENUE_LABEL[venue] ?? venue) : "Not specified"}
              />
              <Fact icon="restaurant" label="Cuisine" value={formatCuisines(cuisines)} />
              {detail?.diet_flags && detail.diet_flags.length > 0 ? (
                <Fact
                  icon="restaurant"
                  label="Diet"
                  value={detail.diet_flags.map((f: string) => f.replace(/_/g, " ")).join(", ")}
                />
              ) : null}
            </FactCard>
          ) : null}

          {item.reason_texts.length > 0 ? (
            <View style={styles.section}>
              <SectionTitle title="Why it is in the plan" />
              {item.reason_texts.map((r) => (
                <Text key={r} style={styles.reason}>
                  • {r}
                </Text>
              ))}
            </View>
          ) : null}

          <View style={styles.actions}>
            <Button
              label="Show on the map"
              icon="map"
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
                  variant="secondary"
                  disabled={items.actions.busyId === item.id}
                  accessibilityLabel={`${item.locked ? "Unlock" : "Lock"} ${item.display_name}`}
                  onPress={() => items.actions.onToggleLock(item)}
                />
                <Button
                  label="Remove"
                  variant="secondary"
                  disabled={items.actions.busyId === item.id || item.locked}
                  accessibilityLabel={`Remove ${item.display_name}`}
                  hint={item.locked ? "Unlock it first." : "Shows what would change first."}
                  onPress={() => items.actions.onRemove(item)}
                />
              </>
            ) : null}
          </View>

          <PlannedFeature
            icon="document"
            title={eat ? "Notes, photos, tickets and reservations" : "Notes, photos and tickets"}
            text={
              eat
                ? "Your notes, photos, attached documents and reservation details for this place will be kept here. Not built yet."
                : "Your notes, photos and attached tickets or documents for this place will be kept here. Not built yet."
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
  heroText: {
    position: "absolute",
    left: spacing.lg,
    right: spacing.lg,
    bottom: spacing.lg,
    gap: spacing.xs,
  },
  heroTitle: { ...type.display, fontSize: 26, lineHeight: 32, color: colors.onImage },
  body: { padding: spacing.lg, gap: spacing.lg },
  tagRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  factCard: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  fact: {
    flexDirection: "row",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  factIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  factText: { flex: 1, gap: spacing.xxs },
  factLabel: { ...type.caption, color: colors.muted },
  factValue: { ...type.body, color: colors.text },
  factNote: { ...type.small, color: colors.muted },
  section: { gap: spacing.xs },
  reason: { ...type.body, color: colors.text },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  source: { ...type.caption, color: colors.muted },
});
