import type { Trip } from "@detour/shared";
import { useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { call, describeError, isOfflineError } from "../api/unwrap";
import { Button } from "../components/Button";
import { Cover } from "../components/ds/Cover";
import { Badge, type BadgeTone, Tabs } from "../components/ds/primitives";
import { ResourceNotices } from "../components/ResourceNotices";
import { EmptyState, ErrorState, LoadingState, ScreenHeader, WakingServer } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import {
  TRIP_PHASE_LABEL,
  type TripPhase,
  type TripTab,
  shortSpan,
  tripPhase,
  tripsInTab,
} from "../domain/trips";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";

/** A past trip opens on its map of visited places (ADR 006); every other trip on its overview,
 * which shows the active plan or leads to the proposals (ADR 021). */
export function tripRoute(trip: Trip): Route {
  if (trip.status === "past") return { name: "pastTrip", tripId: trip.id };
  return { name: "tripOverview", tripId: trip.id };
}

const PHASE_TONE: Record<TripPhase, BadgeTone> = {
  planning: "solid",
  upcoming: "primary",
  inProgress: "accent",
  past: "solid",
};

const CARD_HEIGHT = 148;

/** The cover, then the trip's name, its dates and its length under it (docs/design.md): nothing
 * else, and nothing drawn over the photo but the status. */
export function TripCard({ trip, onPress }: { trip: Trip; onPress: () => void }) {
  const phase = tripPhase(trip);
  const label = TRIP_PHASE_LABEL[phase];
  const span = shortSpan(trip);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${trip.title}. ${span}. ${label}.`}
      accessibilityHint={
        phase === "past"
          ? "Opens the places you visited"
          : phase === "planning"
            ? "Opens the trip, to choose a plan"
            : "Opens the trip and its itinerary"
      }
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
      testID={`trip-card-${trip.id}`}
    >
      <Cover
        seedKey={trip.destination.ref}
        photo={trip.cover_image}
        height={CARD_HEIGHT}
        rounded={radius.lg}
      >
        <View style={styles.cardBadge}>
          <Badge label={label} tone={PHASE_TONE[phase]} />
        </View>
      </Cover>
      <View style={styles.cardText}>
        <Text style={styles.cardTitle} numberOfLines={1}>
          {trip.title}
        </Text>
        <Text style={styles.cardMeta} numberOfLines={1}>
          {span}
        </Text>
      </View>
    </Pressable>
  );
}

const EMPTY_TEXT: Record<TripTab, { title: string; text: string }> = {
  upcoming: {
    title: "No upcoming trips",
    text: "Choose a destination and how many days you have. Detour proposes two different plans to compare.",
  },
  past: {
    title: "No past trips yet",
    text: "A trip moves here two days after its last day, or when you mark it as past in the trip's menu.",
  },
};

export function TripsScreen() {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (client) => call(client.GET("/v1/trips")));
  const [tab, setTab] = useState<TripTab>("upcoming");
  const create = () => nav.push({ name: "createTrip" });

  let body;
  if (trips.data === undefined) {
    if (trips.status === "error") {
      body = isOfflineError(trips.error) ? (
        <ErrorState
          title="You are offline"
          text="No trips are saved on this device yet. Connect to load them."
          onRetry={trips.refresh}
        />
      ) : (
        <ErrorState text={describeError(trips.error)} onRetry={trips.refresh} />
      );
    } else {
      body = trips.waking ? <WakingServer /> : <LoadingState text="Loading your trips…" />;
    }
  } else if (trips.data.length === 0) {
    body = (
      <>
        <ResourceNotices resource={trips} noun="trips" />
        <EmptyState
          title="No trips yet"
          text="Choose a destination and how many days you have. Detour proposes two different plans to compare."
          action={{ label: "Plan a trip", onPress: create }}
        />
      </>
    );
  } else {
    const shown = tripsInTab(trips.data, tab);
    const empty = EMPTY_TEXT[tab];
    body = (
      <>
        <Tabs<TripTab>
          items={[
            { key: "upcoming", label: "Upcoming" },
            { key: "past", label: "Past" },
          ]}
          value={tab}
          onChange={setTab}
          testID="trip-tabs"
        />
        <FlatList
          data={shown}
          keyExtractor={(t) => t.id}
          renderItem={({ item }) => (
            <TripCard trip={item} onPress={() => nav.push(tripRoute(item))} />
          )}
          ListHeaderComponent={<ResourceNotices resource={trips} noun="trips" />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>{empty.title}</Text>
              <Text style={styles.emptyText}>{empty.text}</Text>
            </View>
          }
          ListFooterComponent={
            tab === "upcoming" ? (
              <Button label="New trip" icon="add" variant="ink" fill onPress={create} />
            ) : undefined
          }
          contentContainerStyle={styles.list}
          initialNumToRender={6}
          maxToRenderPerBatch={6}
          windowSize={5}
          refreshControl={
            <RefreshControl
              refreshing={trips.refreshing && !trips.fromCache}
              onRefresh={trips.refresh}
              colors={[colors.primary]}
            />
          }
        />
      </>
    );
  }

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Detour" />
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.lg },
  card: { minHeight: 48, gap: spacing.sm },
  pressed: { opacity: 0.88 },
  cardBadge: { position: "absolute", top: spacing.md, right: spacing.md },
  cardText: { gap: spacing.xxs, paddingHorizontal: spacing.xs },
  cardTitle: { ...type.title, color: colors.text },
  cardMeta: { ...type.small, color: colors.muted, fontWeight: "500" },
  empty: { paddingVertical: spacing.xxl, gap: spacing.sm, alignItems: "center" },
  emptyTitle: { ...type.heading, color: colors.text, textAlign: "center" },
  emptyText: { ...type.body, color: colors.muted, textAlign: "center" },
});
