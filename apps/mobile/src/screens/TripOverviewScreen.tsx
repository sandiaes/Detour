import type { Day, Itinerary, ItineraryVersion, Stay, Trip } from "@detour/shared";
import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { call, describeError } from "../api/unwrap";
import {
  Button,
  Card,
  CompactHeader,
  CoverBar,
  EmptyState,
  ErrorState,
  Icon,
  IconButton,
  ListRow,
  LoadingState,
  Notice,
  RowGroup,
  Sheet,
  type Stat,
  StatRow,
  type TabItem,
  Tabs,
  WakingServer,
  useAnnounceOnMount,
  FocusPressable,
} from "../components/ds";
import { Cover } from "../components/ds/Cover";
import { ResourceNotices } from "../components/ResourceNotices";
import { keys, useTripActions } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { CoverPicker, type CoverSource } from "../components/ds/CoverPicker";
import { isPlaceTrip, placeCoverSource } from "../domain/destinations";
import { useResource } from "../data/DataProvider";
import { useTripCounts } from "../data/tripCounts";
import { dayTotals } from "../domain/itinerary";
import { canOptimize, canUndoOptimize } from "../domain/optimize";
import { type TripCounts, archiveOnly, isReadOnly, localToday, shortSpan } from "../domain/trips";
import { type TripSection, useNavigation } from "../nav/Navigator";
import {
  border,
  colors,
  layout,
  opacity,
  radius,
  size as sizes,
  spacing,
  textOnImage,
  type,
  weight,
} from "../theme";
import { pluralise } from "../util/format";
import { useBackend } from "../api/BackendProvider";
import { PlanDayView, dayTitle } from "../components/plan/DayPlan";
import { useItemActions } from "../data/itemActions";
import { DocumentList } from "../components/documents/DocumentList";
import { TripAlbums } from "../components/photos/TripAlbums";
import { useExtrasActions, useLocalCover } from "../documents/DocumentsProvider";
import { PastTripScreen } from "./PastTripScreen";

// A trip's home (ADR 021): its cover, dates and status, then five tabs. Once a plan is chosen it is
// the trip's active itinerary and the overview is built around it; the original proposals are in
// the trip's menu. A trip without a chosen plan leads to the proposals.

export const TRIP_SECTIONS: TabItem<TripSection>[] = [
  { key: "overview", label: "Overview" },
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
  if (t.meals > 0) parts.push(pluralise(t.meals, "restaurant"));
  return parts.join(" · ");
}

function statsOf(counts: TripCounts): Stat[] {
  const all: (Stat | null)[] = [
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
          icon: "sight",
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

/** The trip's days as a timeline (reference screen 12): a thumbnail, the day, the town and what is
 * planned. A day opens the map of that day. Hairlines, no cards. */
function DayTimeline({
  days,
  coverKey,
  onOpen,
}: {
  days: Day[];
  coverKey: string;
  onOpen: (dayIndex: number) => void;
}) {
  return (
    <View style={styles.timeline}>
      {days.map((day, i) => {
        const title = dayTitle(day);
        const base = day.base_city_name;
        const contents = dayContents(day);
        return (
          <FocusPressable
            key={day.id}
            accessibilityRole="button"
            accessibilityLabel={`${title}.${base ? ` ${base}.` : ""} ${contents}.`}
            accessibilityHint="Opens this day on the map"
            onPress={() => onOpen(day.day_index)}
            style={({ pressed }) => [styles.dayRow, pressed && styles.pressed]}
            testID={`day-row-${day.day_index}`}
          >
            <View style={styles.rail}>
              <View style={[styles.railLine, i === 0 && styles.railLineHidden]} />
              <View style={styles.railDot} />
              <View style={[styles.railLine, i === days.length - 1 && styles.railLineHidden]} />
            </View>
            <View style={[styles.dayCard, i < days.length - 1 && styles.dayCardRule]}>
              <Cover
                seedKey={`${coverKey}:${base ?? day.day_index}`}
                photo={firstPhoto(day)}
                height={sizes.thumb}
                rounded={radius.md}
                credit={false}
                style={styles.thumb}
              />
              <View style={styles.dayText}>
                <Text style={styles.dayTitle}>{title}</Text>
                {base ? <Text style={styles.dayBase}>{base}</Text> : null}
                <Text style={styles.dayMeta}>{contents}</Text>
              </View>
              <Icon name="chevronRight" size="sm" color={colors.muted} />
            </View>
          </FocusPressable>
        );
      })}
    </View>
  );
}

/** Where a trip's cover can be chosen from: its city or area (or, for a multi-city trip, each
 * stop's city, ADR 024). */
export function coverSources(trip: Trip): CoverSource[] {
  const stops = trip.stops ?? [];
  if (stops.length > 0) {
    return stops.map((s) => ({ kind: "city" as const, ref: String(s.city_id), name: s.name }));
  }
  if (trip.destination.kind === "place") {
    // A place has photo candidates only when it came from the gazetteer (ADR 027).
    const source = placeCoverSource(trip);
    return source ? [source] : [];
  }
  const kind = trip.destination.kind === "area" ? "area" : "city";
  return [{ kind, ref: trip.destination.ref, name: trip.destination.name }];
}

/** The Commons file name a photo's page names ("…/wiki/File:Wien_-_Dom.jpg" is "Wien - Dom.jpg"). */
export function commonsFileOf(sourceUrl: string | undefined): string | null {
  const name = sourceUrl?.split("/File:")[1];
  if (!name) return null;
  try {
    return decodeURIComponent(name).replace(/_/g, " ");
  } catch {
    return name.replace(/_/g, " ");
  }
}

/** The photo of the day's first visit that has one (ADR 022, decision 19), else none. */
export function firstPhoto(day: Day) {
  return day.items.find((item) => item.type === "visit" && item.image)?.image ?? null;
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
  day: initialDay,
  itemId: initialItemId,
}: {
  tripId: string;
  section?: TripSection;
  day?: number;
  itemId?: string;
}) {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const { counts, plan } = useTripCounts(trip);
  const insets = useSafeAreaInsets();
  const planId0 = trip?.selected_itinerary_id ?? null;
  const stays = useResource<Stay[]>(
    planId0 ? keys.stays(tripId) : null,
    (c) => call(c.GET("/v1/trips/{trip_id}/stays", { params: { path: { trip_id: tripId } } })),
    { ttlMs: 60_000 },
  );
  const versions = useResource<ItineraryVersion[]>(
    planId0 ? keys.versions(planId0) : null,
    (c) =>
      call(
        c.GET("/v1/itineraries/{itinerary_id}/versions", {
          params: { path: { itinerary_id: planId0 as string } },
        }),
      ),
    { ttlMs: 60_000 },
  );
  const changeActions = useChangeActions();
  const [undoing, setUndoing] = useState<string | null>(null);
  const [section, setSectionState] = useState<TripSection>(initialSection);
  const [menu, setMenu] = useState(false);
  const [picker, setPicker] = useState(false);
  const actions = useTripActions();
  const [dayState, setDayState] = useState<number | null>(initialDay ?? null);
  const [selectedStop, setSelectedStop] = useState<string | null>(initialItemId ?? null);
  // The tabs stick to the top of the screen once the cover has scrolled away.
  const [stuck, setStuck] = useState(false);
  // The section is kept in the route, so coming back from a screen opened on top of this one (a
  // document form, a place) lands on the same tab.
  // The day and the selected stop are kept the same way: Back from a place's details lands on the
  // day and stop the user left, not on the first day.
  const remember = (next: {
    section?: TripSection;
    day?: number | null;
    itemId?: string | null;
  }) => {
    const nextDay = next.day === undefined ? dayState : next.day;
    const nextItem = next.itemId === undefined ? selectedStop : next.itemId;
    nav.replace({
      name: "tripOverview",
      tripId,
      section: next.section ?? section,
      ...(nextDay !== null ? { day: nextDay } : {}),
      ...(nextItem !== null ? { itemId: nextItem } : {}),
    });
  };
  const setSection = (next: TripSection) => {
    setSectionState(next);
    remember({ section: next });
  };
  const setDayIndex = (d: number) => {
    setDayState(d);
    setSelectedStop(null);
    remember({ day: d, itemId: null });
  };
  const titleRef = useAnnounceOnMount();
  const { state } = useBackend();
  const items = useItemActions(tripId, trip?.selected_itinerary_id ?? "");
  const localCover = useLocalCover(tripId);
  const extrasActions = useExtrasActions();

  if (trips.data === undefined) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Trip" onBack={nav.back} />
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
        <CompactHeader title="Trip" onBack={nav.back} />
        <EmptyState
          title="Trip not found"
          text="It may have been deleted."
          action={{ label: "Back to trips", onPress: () => nav.switchRoot({ name: "trips" }) }}
        />
      </View>
    );
  }
  // A past trip of the older archive: its plans are gone, the visited places remain (ADR 006).
  if (archiveOnly(trip)) return <PastTripScreen tripId={tripId} />;

  const hasPlan = trip.selected_itinerary_id !== null;
  const planId = trip.selected_itinerary_id as string;
  // A past trip is read-only (ADR 006, amendment of 2026-11-17).
  const readOnly = isReadOnly(trip);
  const optimizable = !readOnly && hasPlan && plan.data ? canOptimize(plan.data.days) : false;
  const undoable =
    !readOnly && hasPlan && plan.data ? canUndoOptimize(versions.data, plan.data.version) : false;
  const openOptimize = () => nav.push({ name: "optimize", tripId, itineraryId: planId });
  const undoOptimize = async () => {
    setMenu(false);
    try {
      const change = await changeActions.previewOptimizeUndo(planId);
      nav.push({ name: "changePreview", tripId, itineraryId: planId, changeSetId: change.id });
    } catch (e) {
      setUndoing(describeError(e));
    }
  };

  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;
  // The day shown in the Itinerary and Map tabs: today's during the trip, else the first.
  const day =
    dayState ?? (plan.data ? (previewDays(trip, plan.data, undefined, 1)[0]?.day_index ?? 1) : 1);
  const openDay = (d: number, target: TripSection = "map") => {
    setDayState(d);
    setSelectedStop(null);
    setSectionState(target);
    nav.replace({ name: "tripOverview", tripId, section: target, day: d });
  };
  const planView = (mode: "list" | "map") =>
    plan.data ? (
      <PlanDayView
        key={mode}
        days={plan.data.days}
        dayIndex={day}
        onDayChange={setDayIndex}
        mode={mode}
        map={mapConfig}
        stays={stays.data}
        initialSelectedId={selectedStop}
        onSelectionChange={(id) => {
          setSelectedStop(id);
          remember({ itemId: id });
        }}
        onDetails={(item) =>
          nav.push(
            item.type === "transport"
              ? { name: "transportLeg", tripId, itineraryId: planId, itemId: item.id }
              : { name: "placeDetail", tripId, itineraryId: planId, itemId: item.id },
          )
        }
        onShowList={() => setSection("overview")}
      />
    ) : null;

  let content;
  if (section === "photos") {
    content = <TripAlbums trip={trip} />;
  } else if (section === "documents") {
    content = <DocumentList trip={trip} />;
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
    // The overview is the itinerary itself (owner request, 2026-11-15): compact figures, Optimize
    // when it applies, then the days. The original proposals are in the trip menu.
    content = (
      <>
        <ResourceNotices resource={plan} noun="this itinerary" />
        {items.problem ? <Notice tone="error">{items.problem}</Notice> : null}
        {undoing ? <Notice tone="error">{undoing}</Notice> : null}
        {/* The figures' bottom hairline is the Optimize row's top one, so the row has the same
            room above and below it. */}
        {optimizable ? (
          counts ? (
            <View>
              <StatRow stats={statsOf(counts)} />
              <ListRow
                inset="none"
                icon="route"
                title="Optimize"
                detail="Find a shorter order for your stops"
                testID="itinerary-optimize"
                onPress={openOptimize}
              />
            </View>
          ) : (
            <RowGroup>
              <ListRow
                inset="none"
                icon="route"
                title="Optimize"
                detail="Find a shorter order for your stops"
                testID="itinerary-optimize"
                onPress={openOptimize}
              />
            </RowGroup>
          )
        ) : counts ? (
          <StatRow stats={statsOf(counts)} />
        ) : null}
        <DayTimeline
          days={[...plan.data.days].sort((x, y) => x.day_index - y.day_index)}
          coverKey={trip.destination.ref}
          onOpen={(d) => openDay(d, "map")}
        />
      </>
    );
  }

  const menuSheet = menu ? (
    <Sheet visible title="Trip menu" onClose={() => setMenu(false)}>
      <RowGroup>
        {isPlaceTrip(trip) || readOnly ? null : (
          <ListRow
            inset="none"
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
        )}
        <ListRow
          inset="none"
          icon="photos"
          title="Change photo"
          detail={
            readOnly || coverSources(trip).length === 0
              ? "Choose the trip's cover from your phone"
              : "Choose the trip's cover from your phone or photos of the destination"
          }
          testID="menu-change-photo"
          onPress={() => {
            setMenu(false);
            setPicker(true);
          }}
        />
        {readOnly ? null : (
          <ListRow
            inset="none"
            icon="home"
            title="Where you're staying"
            detail="Each day starts at your stay"
            testID="menu-stays"
            onPress={() => {
              setMenu(false);
              nav.push({ name: "stays", tripId });
            }}
          />
        )}
        {optimizable ? (
          <ListRow
            inset="none"
            icon="route"
            title="Optimize"
            detail="Find a shorter order for your stops"
            testID="menu-optimize"
            onPress={() => {
              setMenu(false);
              openOptimize();
            }}
          />
        ) : null}
        {undoable ? (
          <ListRow
            inset="none"
            icon="history"
            title="Undo Optimize"
            detail="Put the stops back in the order they had"
            testID="menu-undo-optimize"
            onPress={() => void undoOptimize()}
          />
        ) : null}
        <ListRow
          inset="none"
          icon="export"
          title="Export trip"
          detail="A file with this trip, to keep or share"
          testID="menu-export"
          onPress={() => {
            setMenu(false);
            nav.push({ name: "exportTrips", tripId });
          }}
        />
        <ListRow
          inset="none"
          icon="settings"
          title="Trip settings"
          detail={
            readOnly
              ? "Reopen, delete"
              : isPlaceTrip(trip)
                ? "Mark as past, delete"
                : "New proposals, mark as past, delete"
          }
          testID="menu-settings"
          onPress={() => {
            setMenu(false);
            nav.push({ name: "tripSettings", tripId });
          }}
        />
      </RowGroup>
    </Sheet>
  ) : null;

  const pickerSheet = picker ? (
    <CoverPicker
      visible
      sources={readOnly ? [] : coverSources(trip)}
      load={actions.coverCandidates}
      chosen={localCover ? null : commonsFileOf(trip.cover_image?.credit.source_url)}
      local={localCover !== null}
      onPickLocal={async () => {
        const picked = await extrasActions.pickImage();
        if (!picked) return false;
        await extrasActions.setLocalCover(trip.id, picked);
        return true;
      }}
      onChoose={async (c) => {
        // A destination photo (or the automatic one) replaces a picture from the phone.
        if (!readOnly && coverSources(trip).length > 0) {
          await actions.setCover(trip.id, c?.commons_file ?? null);
          trips.refresh();
        }
        await extrasActions.clearLocalCover(trip.id);
      }}
      onClose={() => setPicker(false)}
    />
  ) : null;

  const tabsFor = (compact: boolean) => (
    <Tabs<TripSection>
      items={TRIP_SECTIONS}
      value={section}
      onChange={setSection}
      compact={compact}
      testID="trip-sections"
    />
  );
  const tabs = tabsFor(false);

  const compactHead = (
    // Above the map in drawing order too (zIndex and elevation), with its own background: markers
    // dragged past the map's edge can never show over the back button, the title or the tabs.
    <View style={styles.compactHeadWrap}>
      <CompactHeader
        title={trip.title}
        onBack={nav.back}
        right={
          <IconButton
            icon="dots"
            label="Trip menu"
            hint="Original proposals and trip settings"
            size="sm"
            testID="trip-menu"
            onPress={() => setMenu(true)}
          />
        }
      />
      {tabsFor(false)}
    </View>
  );
  // Only the Map tab leaves the cover behind (it needs the room): a compact header, the tabs, then
  // the map of one day with its stops beneath. Overview and Itinerary share one layout: the trip's
  // header, its photo, then the tabs and their content on a sheet.
  if (section === "map" && hasPlan && plan.data) {
    return (
      <View style={styles.fill}>
        {compactHead}
        {items.problem ? (
          <Notice inset tone="error">
            {items.problem}
          </Notice>
        ) : null}
        {planView("map")}
        {menuSheet}
        {pickerSheet}
      </View>
    );
  }
  return (
    // The cover reaches the very top of the screen, under the status bar.
    <View style={[styles.fill, { marginTop: -insets.top }]}>
      <StatusBar style={stuck ? "dark" : "light"} />
      <ScrollView
        contentContainerStyle={styles.scroll}
        stickyHeaderIndices={[1]}
        scrollEventThrottle={32}
        onScroll={(e) => {
          const isStuck = e.nativeEvent.contentOffset.y >= COVER_HEIGHT + insets.top - SHEET_RADIUS;
          if (isStuck !== stuck) setStuck(isStuck);
        }}
      >
        <Cover
          seedKey={trip.destination.ref}
          photo={trip.cover_image}
          uri={localCover?.uri ?? null}
          height={COVER_HEIGHT + insets.top}
          scrim
          creditInset={SHEET_RADIUS}
          testID="trip-cover"
        >
          <CoverBar
            top={insets.top}
            onBack={nav.back}
            right={
              <IconButton
                icon="dots"
                label="Trip menu"
                hint="Original proposals and trip settings"
                variant="onImage"
                testID="trip-menu"
                onPress={() => setMenu(true)}
              />
            }
          />
          <View
            ref={titleRef}
            style={styles.heroText}
            accessible
            accessibilityRole="header"
            accessibilityLabel={`${trip.title}. ${shortSpan(trip)}.`}
          >
            <Text style={styles.heroTitle} numberOfLines={2}>
              {trip.title}
            </Text>
            <Text style={styles.heroMeta} numberOfLines={1}>
              {shortSpan(trip)}
            </Text>
          </View>
        </Cover>
        {/* The tabs and what follows sit on a white sheet whose top corners curve over the photo. */}
        <View style={[styles.sheetTop, stuck && { paddingTop: insets.top }]}>{tabs}</View>
        <View style={styles.sheetBody}>
          <View style={styles.body2}>
            <ResourceNotices resource={trips} noun="trips" />
            {content}
          </View>
        </View>
      </ScrollView>
      {menuSheet}
      {pickerSheet}
    </View>
  );
}

const COVER_HEIGHT = 260;
const SHEET_RADIUS = radius.xl;

const styles = StyleSheet.create({
  fill: { flex: 1 },
  flex: { flex: 1 },
  scroll: { paddingBottom: spacing.xxl },
  pressed: { opacity: opacity.pressed },
  // The trip's name, dates and length sit on its photo, bottom left, above the curve of the sheet
  // (reference screen 02). Back and the menu sit on it at the top.
  heroText: {
    position: "absolute",
    left: layout.gutter,
    right: layout.gutter,
    bottom: SHEET_RADIUS + spacing.sm,
    gap: spacing.xxs,
  },
  heroTitle: { ...type.hero, ...textOnImage },
  heroMeta: { ...type.label, fontWeight: weight.semibold, ...textOnImage },
  sheetTop: {
    marginTop: -SHEET_RADIUS,
    backgroundColor: colors.background,
    borderTopLeftRadius: SHEET_RADIUS,
    borderTopRightRadius: SHEET_RADIUS,
    overflow: "hidden",
  },
  sheetBody: { backgroundColor: colors.background },
  body2: {
    paddingHorizontal: layout.gutter,
    paddingTop: spacing.sm,
    paddingBottom: spacing.lg,
    gap: layout.block,
  },
  cardTitle: { ...type.cardTitle, color: colors.text },
  body: { ...type.label, color: colors.text },
  timeline: {},
  compactHeadWrap: { zIndex: 3, elevation: 3, backgroundColor: colors.background },
  dayRow: { flexDirection: "row", minHeight: sizes.row },
  rail: { width: 20, alignItems: "center" },
  railLine: { flex: 1, width: border.thick, backgroundColor: colors.border },
  railLineHidden: { backgroundColor: "transparent" },
  railDot: {
    width: 10,
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
  },
  dayCard: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginLeft: spacing.sm,
    paddingVertical: spacing.sm,
  },
  dayCardRule: { borderBottomWidth: border.hairline, borderBottomColor: colors.border },
  thumb: { width: sizes.thumb },
  dayText: { flex: 1, gap: spacing.xxs },
  dayTitle: { ...type.label, fontWeight: weight.bold, color: colors.text },
  dayBase: { ...type.label, color: colors.text },
  dayMeta: { ...type.caption, color: colors.muted },
});
