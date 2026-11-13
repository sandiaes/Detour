import type { Trip } from "@detour/shared";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { call, describeError, isOfflineError } from "../api/unwrap";
import { Button } from "../components/Button";
import { ResourceNotices } from "../components/ResourceNotices";
import { EmptyState, ErrorState, LoadingState, ScreenHeader, WakingServer } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, radius, spacing, type } from "../theme";
import { formatTripSpan } from "../util/format";

export function TripCard({ trip, onPress }: { trip: Trip; onPress: () => void }) {
  const span = formatTripSpan(trip.start_date, trip.end_date, trip.duration_days);
  const status =
    trip.status === "past"
      ? "Past trip"
      : trip.selected_itinerary_id
        ? "✓ Plan selected"
        : "No plan chosen yet";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${trip.title}. ${trip.destination.name}. ${span}. ${status.replace("✓ ", "")}.`}
      accessibilityHint="Opens the trip"
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <Text style={styles.cardTitle}>{trip.title}</Text>
      <Text style={styles.cardMeta}>{trip.destination.name}</Text>
      <Text style={styles.cardMeta}>{span}</Text>
      <Text style={[styles.cardStatus, trip.selected_itinerary_id ? styles.statusOn : null]}>
        {status}
      </Text>
    </Pressable>
  );
}

export function TripsScreen() {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (client) => call(client.GET("/v1/trips")));
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
    body = (
      <FlatList
        data={trips.data}
        keyExtractor={(t) => t.id}
        renderItem={({ item }) => (
          <TripCard trip={item} onPress={() => nav.push({ name: "trip", tripId: item.id })} />
        )}
        ListHeaderComponent={<ResourceNotices resource={trips} noun="trips" />}
        contentContainerStyle={styles.list}
        initialNumToRender={8}
        maxToRenderPerBatch={8}
        windowSize={5}
        refreshControl={
          <RefreshControl
            refreshing={trips.refreshing && !trips.fromCache}
            onRefresh={trips.refresh}
            colors={[colors.primary]}
          />
        }
      />
    );
  }

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Trips" right={<Button label="New trip" onPress={create} />} />
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 48,
  },
  pressed: { opacity: 0.85 },
  cardTitle: { ...type.heading, color: colors.text },
  cardMeta: { ...type.small, color: colors.muted },
  cardStatus: { ...type.small, color: colors.muted, marginTop: spacing.xs, fontWeight: "600" },
  statusOn: { color: colors.primary },
});
