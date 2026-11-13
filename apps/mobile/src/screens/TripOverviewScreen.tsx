import type { Day, Itinerary, Trip } from "@detour/shared";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Cover } from "../components/ds/Cover";
import { Icon } from "../components/ds/Icon";
import {
  Badge,
  IconButton,
  ListRow,
  PlannedFeature,
  RowGroup,
  SectionTitle,
  Sheet,
  type Stat,
  StatRow,
  type TabItem,
  Tabs,
} from "../components/ds/primitives";
import { ResourceNotices } from "../components/ResourceNotices";
import {
  Card,
  Chip,
  EmptyState,
  ErrorState,
  LoadingState,
  ScreenHeader,
  WakingServer,
  useAnnounceOnMount,
} from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useTripCounts } from "../data/tripCounts";
import { PROFILE_EMPHASIS, PROFILE_LABEL, planFacts } from "../domain/compare";
import { dayTotals } from "../domain/itinerary";
import {
  TRIP_PHASE_LABEL,
  type TripCounts,
  localToday,
  shortSpan,
  tripPhase,
} from "../domain/trips";
import { type TripSection, useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { pluralise } from "../util/format";
import { dayTitle } from "./ItineraryScreen";
import { PastTripScreen } from "./PastTripScreen";

// A trip's home (ADR 021): its cover, dates and status, then five tabs. Once a plan is chosen it is
// the trip's active itinerary and the overview is built around it; the original proposals are in
// the trip's menu. A trip without a chosen plan leads to the proposals.

export const TRIP_SECTIONS: TabItem<TripSection>[] = [
  { key: "overview", label: "Overview" },
  { key: "itinerary", label: "Itinerary" },
  { key: "map", label: "Map" },
  // Named in full: the bottom bar has a Photos tab of its own.
  { key: "photos", label: "Photos", accessibilityLabel: "Trip photos" },
  { key: "documents", label: "Documents", accessibilityLabel: "Trip documents" },
];

/** Days to preview on the overview: from today's day during the trip, otherwise from day 1. */
export function previewDays(trip: Trip, plan: Itinerary, today = localToday(), max = 3): Day[] {
  const days = [...plan.days].sort((a, b) => a.day_index - b.day_index);
  const current = days.findIndex((d) => d.date === today);
  return days.slice(current >= 0 ? current : 0).slice(0, max);
}

/** "3 activities · 1 restaurant" for a day, from the plan's own items. */
export function dayContents(day: Day): string {
  const t = dayTotals(day);
  if (t.visits === 0 && t.meals === 0) return "Nothing planned";
  const parts = [pluralise(t.visits, "activity", "activities")];
  if (t.meals > 0) parts.push(pluralise(t.meals, "meal"));
  return parts.join(" · ");
}

function statsOf(counts: TripCounts): Stat[] {
  const all: (Stat | null)[] = [
    {
      key: "days",
      icon: "calendar",
      value: counts.days,
      label: counts.days === 1 ? "Day" : "Days",
    },
    counts.cities !== null
      ? {
          key: "cities",
          icon: "city",
          value: counts.cities,
          label: counts.cities === 1 ? "City" : "Cities",
        }
      : null,
    counts.places !== null
      ? {
          key: "places",
          icon: "attraction",
          value: counts.places,
          label: counts.places === 1 ? "Place" : "Places",
        }
      : null,
    counts.restaurants !== null
      ? {
          key: "restaurants",
          icon: "restaurant",
          value: counts.restaurants,
          label: counts.restaurants === 1 ? "Restaurant" : "Restaurants",
        }
      : null,
  ];
  return all.filter((s): s is Stat => s !== null);
}

function DayTimeline({ trip, days }: { trip: Trip; days: Day[] }) {
  const nav = useNavigation();
  const planId = trip.selected_itinerary_id as string;
  return (
    <View style={styles.timeline}>
      {days.map((day, i) => {
        const title = dayTitle(day);
        const base = day.base_city_name;
        const contents = dayContents(day);
        return (
          <Pressable
            key={day.id}
            accessibilityRole="button"
            accessibilityLabel={`${title}.${base ? ` ${base}.` : ""} ${contents}.`}
            accessibilityHint="Opens this day of the itinerary"
            onPress={() =>
              nav.push({
                name: "itinerary",
                tripId: trip.id,
                itineraryId: planId,
                view: "days",
                day: day.day_index,
              })
            }
            style={({ pressed }) => [styles.dayRow, pressed && styles.pressed]}
            testID={`day-row-${day.day_index}`}
          >
            <View style={styles.rail}>
              <View style={[styles.railLine, i === 0 && styles.railLineHidden]} />
              <View style={styles.railDot} />
              <View style={[styles.railLine, i === days.length - 1 && styles.railLineHidden]} />
            </View>
            <View style={styles.dayCard}>
              <View style={styles.dayText}>
                <Text style={styles.dayTitle}>{title}</Text>
                {base ? <Text style={styles.dayBase}>{base}</Text> : null}
                <Text style={styles.dayMeta}>{contents}</Text>
              </View>
              <Icon name="chevronRight" size={18} color={colors.muted} />
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

function ChoosePlanCard({ trip }: { trip: Trip }) {
  const nav = useNavigation();
  return (
    <Card>
      <Text accessibilityRole="header" style={styles.cardTitle}>
        Choose a plan
      </Text>
      <Text style={styles.body}>
        Detour proposes two different plans for {trip.destination.name}: one of the best-known
        sights and one that covers more. The one you choose becomes this trip&apos;s itinerary.
      </Text>
      <Button
        label="See the proposals"
        testID="open-proposals"
        onPress={() => nav.push({ name: "trip", tripId: trip.id })}
      />
    </Card>
  );
}

function PlanLoading({ plan }: { plan: ReturnType<typeof useTripCounts>["plan"] }) {
  if (plan.status === "error") {
    return (
      <ErrorState
        title={plan.offline ? "You are offline" : "Could not load the itinerary"}
        text={
          plan.offline
            ? "This itinerary is not saved on the device yet. Connect once to open it, and it will be available offline afterwards."
            : describeError(plan.error)
        }
        onRetry={plan.refresh}
      />
    );
  }
  return plan.waking ? <WakingServer /> : <LoadingState text="Loading the itinerary…" />;
}

export function TripOverviewScreen({
  tripId,
  section: initialSection = "overview",
}: {
  tripId: string;
  section?: TripSection;
}) {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const { counts, plan } = useTripCounts(trip);
  const [section, setSection] = useState<TripSection>(initialSection);
  const [menu, setMenu] = useState(false);
  const titleRef = useAnnounceOnMount();

  if (trips.data === undefined) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Trip" onBack={nav.back} />
        {trips.status === "error" ? (
          <ErrorState text={describeError(trips.error)} onRetry={trips.refresh} />
        ) : trips.waking ? (
          <WakingServer />
        ) : (
          <LoadingState text="Loading the trip…" />
        )}
      </View>
    );
  }
  if (!trip) {
    return (
      <View style={styles.fill}>
        <ScreenHeader title="Trip" onBack={nav.back} />
        <EmptyState
          title="Trip not found"
          text="It may have been deleted."
          action={{ label: "Back to trips", onPress: () => nav.switchRoot({ name: "trips" }) }}
        />
      </View>
    );
  }
  // A trip that became past while open: its plans are gone, the visited places remain (ADR 006).
  if (trip.status === "past") return <PastTripScreen tripId={tripId} />;

  const phase = tripPhase(trip);
  const hasPlan = trip.selected_itinerary_id !== null;
  const planId = trip.selected_itinerary_id as string;
  const openPlan = (view: "days" | "map", day = 1) =>
    nav.push({ name: "itinerary", tripId, itineraryId: planId, view, day });

  let content;
  if (section === "photos") {
    content = (
      <PlannedFeature
        icon="photos"
        title="Photos are planned"
        text="Photos of this trip, grouped by day or place, will appear here. Adding photos from the device or from Google Photos is not built yet."
        testID="trip-photos-planned"
      />
    );
  } else if (section === "documents") {
    content = (
      <PlannedFeature
        icon="document"
        title="Documents are planned"
        text="Tickets, bookings, transport documents and insurance, each linked to the trip or to a place, day or journey, will be kept here. Not built yet."
        testID="trip-documents-planned"
      />
    );
  } else if (!hasPlan) {
    content = (
      <>
        {section === "overview" && counts ? <StatRow stats={statsOf(counts)} /> : null}
        <ChoosePlanCard trip={trip} />
      </>
    );
  } else if (!plan.data) {
    content = <PlanLoading plan={plan} />;
  } else if (section === "overview") {
    const data = plan.data;
    content = (
      <>
        <ResourceNotices resource={plan} noun="this itinerary" />
        {counts ? <StatRow stats={statsOf(counts)} /> : null}
        <Card>
          <View style={styles.planHead}>
            <Text accessibilityRole="header" style={styles.cardTitle}>
              Your itinerary
            </Text>
            <Badge label={`${PROFILE_LABEL[data.profile]} plan`} tone="primary" />
          </View>
          <Text style={styles.body}>{PROFILE_EMPHASIS[data.profile]}</Text>
          <Text style={styles.meta}>{planFacts(data).join(" · ")}</Text>
          <View style={styles.actions}>
            <Button
              label="Itinerary"
              icon="list"
              testID="open-itinerary"
              accessibilityLabel="Open the itinerary"
              onPress={() => openPlan("days")}
            />
            <Button
              label="Map"
              icon="map"
              variant="secondary"
              testID="open-map"
              accessibilityLabel="Open the itinerary map"
              onPress={() => openPlan("map")}
            />
          </View>
        </Card>
        <SectionTitle
          title={phase === "inProgress" ? "Today and next" : "First days"}
          action={
            data.days.length > 3 ? (
              <Button
                label="All days"
                variant="quiet"
                accessibilityLabel="Show all days"
                onPress={() => setSection("itinerary")}
              />
            ) : undefined
          }
        />
        <DayTimeline trip={trip} days={previewDays(trip, data)} />
        <PlannedFeature
          icon="note"
          title="Notes and reservations"
          text="Your notes and the next reservations of this trip will be shown here. Not built yet."
          testID="notes-planned"
        />
      </>
    );
  } else if (section === "itinerary") {
    const days = [...plan.data.days].sort((a, b) => a.day_index - b.day_index);
    content = (
      <>
        <ResourceNotices resource={plan} noun="this itinerary" />
        <SectionTitle
          title={pluralise(days.length, "day")}
          action={
            <Button
              label="Full day list"
              variant="quiet"
              accessibilityLabel="Open the full day list"
              onPress={() => openPlan("days")}
            />
          }
        />
        <DayTimeline trip={trip} days={days} />
      </>
    );
  } else {
    const days = [...plan.data.days].sort((a, b) => a.day_index - b.day_index);
    content = (
      <Card>
        <View style={styles.planHead}>
          <Icon name="map" color={colors.primary} />
          <Text accessibilityRole="header" style={[styles.cardTitle, styles.flex]}>
            Map of each day
          </Text>
        </View>
        <Text style={styles.body}>
          Sights are green circles and places to eat orange squares, numbered in the order of the
          day. Choose a day to open its map.
        </Text>
        <View style={styles.chips}>
          {days.map((d) => (
            <Chip
              key={d.id}
              label={`Day ${d.day_index}`}
              selected={false}
              accessibilityLabel={`Open the map of day ${d.day_index}`}
              onPress={() => openPlan("map", d.day_index)}
            />
          ))}
        </View>
      </Card>
    );
  }

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.scroll} stickyHeaderIndices={[1]}>
        <Cover seedKey={trip.destination.ref} height={248} testID="trip-cover">
          <View style={styles.heroTop}>
            <IconButton icon="back" label="Back" onImage onPress={nav.back} />
            <IconButton
              icon="dots"
              label="Trip menu"
              hint="Original proposals and trip settings"
              onImage
              testID="trip-menu"
              onPress={() => setMenu(true)}
            />
          </View>
          <View style={styles.heroText}>
            <Badge
              label={TRIP_PHASE_LABEL[phase]}
              tone={phase === "inProgress" ? "accent" : phase === "upcoming" ? "primary" : "solid"}
            />
            <View
              ref={titleRef}
              accessible
              accessibilityRole="header"
              accessibilityLabel={trip.title}
            >
              <Text style={styles.heroTitle} numberOfLines={2}>
                {trip.title}
              </Text>
            </View>
            <View style={styles.heroMeta}>
              <Icon name="calendar" size={16} color={colors.onImage} />
              <Text style={styles.heroMetaText}>{shortSpan(trip)}</Text>
            </View>
            <View style={styles.heroMeta}>
              <Icon name="pin" size={16} color={colors.onImage} />
              <Text style={styles.heroMetaText}>{trip.destination.name}</Text>
            </View>
          </View>
        </Cover>
        <View style={styles.tabs}>
          <Tabs<TripSection>
            items={TRIP_SECTIONS}
            value={section}
            onChange={setSection}
            scrollable
            testID="trip-sections"
          />
        </View>
        <ResourceNotices resource={trips} noun="trips" />
        <View style={styles.body2}>{content}</View>
      </ScrollView>
      {menu ? (
        <Sheet visible title="Trip menu" onClose={() => setMenu(false)}>
          <RowGroup>
            <ListRow
              icon="history"
              title={hasPlan ? "Original proposals" : "Proposals"}
              detail={
                hasPlan
                  ? "The plans Detour proposed for this trip"
                  : "Compare the two plans and choose one"
              }
              testID="menu-proposals"
              onPress={() => {
                setMenu(false);
                nav.push({ name: "trip", tripId });
              }}
            />
            <ListRow
              icon="settings"
              title="Trip settings"
              detail="New proposals, mark as past, delete"
              testID="menu-settings"
              onPress={() => {
                setMenu(false);
                nav.push({ name: "tripSettings", tripId });
              }}
            />
          </RowGroup>
        </Sheet>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  flex: { flex: 1 },
  scroll: { paddingBottom: spacing.xxl },
  pressed: { opacity: 0.8 },
  heroTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  heroText: {
    position: "absolute",
    left: spacing.lg,
    right: spacing.lg,
    bottom: spacing.lg,
    gap: spacing.xs,
  },
  heroTitle: { ...type.display, color: colors.onImage },
  heroMeta: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  heroMetaText: { ...type.small, color: colors.onImage, fontWeight: "500" },
  tabs: { backgroundColor: colors.background },
  body2: { padding: spacing.lg, gap: spacing.lg },
  cardTitle: { ...type.heading, color: colors.text },
  body: { ...type.body, color: colors.text },
  meta: { ...type.small, color: colors.muted },
  planHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  timeline: {},
  dayRow: { flexDirection: "row", minHeight: 72 },
  rail: { width: 24, alignItems: "center" },
  railLine: { flex: 1, width: 2, backgroundColor: colors.border },
  railLineHidden: { backgroundColor: "transparent" },
  railDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.primary,
    backgroundColor: colors.surface,
  },
  dayCard: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    marginLeft: spacing.sm,
    marginVertical: spacing.xs,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  dayText: { flex: 1, gap: spacing.xxs },
  dayTitle: { ...type.body, fontWeight: "700", color: colors.text },
  dayBase: { ...type.small, color: colors.text },
  dayMeta: { ...type.small, color: colors.muted },
});
