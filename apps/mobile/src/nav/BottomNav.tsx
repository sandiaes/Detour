import type { Trip } from "@detour/shared";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { call } from "../api/unwrap";
import { Icon, type IconName, ListRow, RowGroup, Sheet, useFocusRing } from "../components/ds";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { TOUCH, colors, radius, size as sizes, spacing, type, weight } from "../theme";
import { type RootName, type Route, useNavigation } from "./Navigator";

// The bottom navigation (ADR 021): Trips, Explore, Add, Photos, More. Add is contextual: outside a
// trip it starts a new trip; inside one it offers what can be added to that trip.

const TABS: { key: RootName; label: string; icon: IconName }[] = [
  { key: "trips", label: "Trips", icon: "trips" },
  { key: "explore", label: "Explore", icon: "explore" },
  { key: "photos", label: "Photos", icon: "photos" },
  { key: "more", label: "More", icon: "more" },
];

/** Screens of one trip on which the bottom bar stays visible, with Add acting on that trip. */
const TRIP_SCREENS = new Set<Route["name"]>(["tripOverview", "itinerary", "pastTrip"]);

/** Whether the bar is shown: on the root tabs and on a trip's main screens, not on forms. */
export function showsBottomNav(route: Route, depth: number): boolean {
  return depth === 1 || TRIP_SCREENS.has(route.name);
}

/** The trip the current screen belongs to, if any. */
export function tripContext(route: Route): string | null {
  return TRIP_SCREENS.has(route.name) && "tripId" in route ? (route.tripId ?? null) : null;
}

function rootOf(route: Route): RootName {
  if (route.name === "explore" || route.name === "photos" || route.name === "more") {
    return route.name;
  }
  return route.name === "settings" ? "more" : "trips";
}

/** One place in the bar: a tab (selected is colour, weight and a bar, and announced) or the Add disc. */
function NavItem({
  label,
  icon,
  selected = false,
  add = false,
  accessibilityLabel,
  hint,
  onPress,
  testID,
}: {
  label: string;
  icon: IconName;
  selected?: boolean;
  add?: boolean;
  accessibilityLabel?: string;
  hint?: string;
  onPress: () => void;
  testID: string;
}) {
  const focus = useFocusRing();
  return (
    <Pressable
      accessibilityRole={add ? "button" : "tab"}
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={hint}
      accessibilityState={add ? undefined : { selected }}
      style={[styles.item, focus.ring]}
      onPress={onPress}
      {...focus.focusProps}
      testID={testID}
    >
      {add ? (
        <View style={styles.addDisc}>
          <Icon name="add" size="lg" color={colors.onPrimary} />
        </View>
      ) : (
        <Icon name={icon} size="lg" color={selected ? colors.selected : colors.muted} />
      )}
      <Text style={[styles.label, selected && styles.labelActive]}>{label}</Text>
      {add ? null : <View style={[styles.marker, selected && styles.markerActive]} />}
    </Pressable>
  );
}

export function BottomNav() {
  const nav = useNavigation();
  const [adding, setAdding] = useState(false);
  const tripId = tripContext(nav.route);
  const active = rootOf(nav.route);

  const onAdd = () => {
    if (tripId) setAdding(true);
    else nav.push({ name: "createTrip" });
  };

  const tab = (t: (typeof TABS)[number]) => (
    <NavItem
      key={t.key}
      label={t.label}
      icon={t.icon}
      selected={active === t.key}
      onPress={() => nav.switchRoot({ name: t.key })}
      testID={`nav-${t.key}`}
    />
  );

  return (
    <>
      <View style={styles.bar} accessibilityRole="tablist">
        {tab(TABS[0] as (typeof TABS)[number])}
        {tab(TABS[1] as (typeof TABS)[number])}
        <NavItem
          label="Add"
          icon="add"
          add
          accessibilityLabel={tripId ? "Add to this trip" : "Add a trip"}
          hint={tripId ? "Choose what to add: a place, a restaurant, and more" : "Plan a new trip"}
          onPress={onAdd}
          testID="nav-add"
        />
        {tab(TABS[2] as (typeof TABS)[number])}
        {tab(TABS[3] as (typeof TABS)[number])}
      </View>
      {tripId && adding ? (
        <AddToTripSheet tripId={tripId} onClose={() => setAdding(false)} />
      ) : null}
    </>
  );
}

/** What can be added to a trip. Places and restaurants go through the existing adjustment flow. */
export function AddToTripSheet({ tripId, onClose }: { tripId: string; onClose: () => void }) {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  const planId = trip?.status === "past" ? null : (trip?.selected_itinerary_id ?? null);
  const why =
    trip?.status === "past"
      ? "A past trip cannot be changed"
      : !planId
        ? "Choose a plan first"
        : undefined;

  const go = (route: Route) => {
    onClose();
    nav.push(route);
  };
  // The day open on the trip's map or day list, if one is.
  const open = nav.route;
  const day =
    (open.name === "tripOverview" || open.name === "itinerary") && open.day !== undefined
      ? { day: open.day }
      : {};

  return (
    <Sheet visible title="Add to this trip" onClose={onClose}>
      <RowGroup>
        <ListRow
          icon="attraction"
          title="Place"
          detail={why ?? "A sight, town, address or pin; Detour suggests the best days"}
          disabled={!planId}
          disabledLabel="Not now"
          testID="add-sheet-place"
          onPress={
            planId ? () => go({ name: "addPlace", tripId, itineraryId: planId, ...day }) : undefined
          }
        />
        <ListRow
          icon="restaurant"
          title="Restaurant"
          detail={why ?? "Detour suggests the best day and meal"}
          disabled={!planId}
          disabledLabel="Not now"
          testID="add-sheet-restaurant"
          onPress={
            planId
              ? () => go({ name: "addRestaurant", tripId, itineraryId: planId, ...day })
              : undefined
          }
        />
        <ListRow icon="transport" title="Transport" detail="A train, bus or drive" disabled />
        <ListRow icon="note" title="Note" detail="Something to remember" disabled />
        <ListRow
          icon="document"
          title="Document"
          detail="A ticket, booking or transport document, kept on this phone"
          testID="add-sheet-document"
          onPress={() => go({ name: "documentForm", tripId })}
        />
      </RowGroup>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    // The page's own colour, no line and no shadow: it melts into the page.
    backgroundColor: colors.background,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xs,
  },
  item: {
    flex: 1,
    minHeight: TOUCH + spacing.sm,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xxs,
  },
  label: { ...type.micro, color: colors.muted, fontWeight: weight.medium },
  labelActive: { color: colors.selected, fontWeight: weight.bold },
  marker: { height: 3, width: 20, borderRadius: radius.pill, backgroundColor: "transparent" },
  markerActive: { backgroundColor: colors.selected },
  addDisc: {
    width: sizes.tile,
    height: sizes.tile,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.primary,
  },
});
