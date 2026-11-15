import type { Trip } from "@detour/shared";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { call } from "../api/unwrap";
import { Icon, type IconName } from "../components/ds/Icon";
import { ListRow, RowGroup, Sheet } from "../components/ds/primitives";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { TOUCH, colors, spacing, type } from "../theme";
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

export function BottomNav() {
  const nav = useNavigation();
  const [adding, setAdding] = useState(false);
  const tripId = tripContext(nav.route);
  const active = rootOf(nav.route);

  const onAdd = () => {
    if (tripId) setAdding(true);
    else nav.push({ name: "createTrip" });
  };

  const tab = (t: (typeof TABS)[number]) => {
    const selected = active === t.key;
    return (
      <Pressable
        key={t.key}
        accessibilityRole="tab"
        accessibilityLabel={t.label}
        accessibilityState={{ selected }}
        style={styles.item}
        onPress={() => nav.switchRoot({ name: t.key })}
        testID={`nav-${t.key}`}
      >
        <Icon name={t.icon} color={selected ? colors.primary : colors.muted} />
        <Text style={[styles.label, selected && styles.labelActive]}>{t.label}</Text>
        {/* Selected is shown by colour, weight and this bar, and announced. */}
        <View style={[styles.marker, selected && styles.markerActive]} />
      </Pressable>
    );
  };

  return (
    <>
      <View style={styles.bar} accessibilityRole="tablist">
        {tab(TABS[0] as (typeof TABS)[number])}
        {tab(TABS[1] as (typeof TABS)[number])}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={tripId ? "Add to this trip" : "Add a trip"}
          accessibilityHint={
            tripId ? "Choose what to add: a place, a restaurant, and more" : "Plan a new trip"
          }
          style={styles.item}
          onPress={onAdd}
          testID="nav-add"
        >
          <View style={styles.addDisc}>
            <Icon name="add" color={colors.onPrimary} strokeWidth={2.2} />
          </View>
          <Text style={styles.label}>Add</Text>
        </Pressable>
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
          onPress={planId ? () => go({ name: "addPlace", tripId, itineraryId: planId }) : undefined}
        />
        <ListRow
          icon="restaurant"
          title="Restaurant"
          detail={why ?? "Detour suggests the best day and meal"}
          disabled={!planId}
          disabledLabel="Not now"
          testID="add-sheet-restaurant"
          onPress={
            planId ? () => go({ name: "addRestaurant", tripId, itineraryId: planId }) : undefined
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
    minHeight: TOUCH + 8,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xxs,
  },
  label: { ...type.caption, fontSize: 12, color: colors.muted, fontWeight: "500" },
  labelActive: { color: colors.primary, fontWeight: "700" },
  marker: { height: 3, width: 20, borderRadius: 2, backgroundColor: "transparent" },
  markerActive: { backgroundColor: colors.primary },
  addDisc: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.primary,
  },
});
