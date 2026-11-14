import type { Trip } from "@detour/shared";
import { ScrollView, StyleSheet, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { DocumentList } from "../components/documents/DocumentList";
import { ErrorState, LoadingState, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { spacing } from "../theme";

/** A trip's documents as a screen of their own: how a past trip reaches them (ADR 023). */
export function TripDocumentsScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === tripId);
  return (
    <View style={styles.fill}>
      <ScreenHeader title="Documents" subtitle={trip?.title} onBack={nav.back} />
      {trip ? (
        <ScrollView contentContainerStyle={styles.content}>
          <DocumentList trip={trip} />
        </ScrollView>
      ) : trips.status === "error" ? (
        <ErrorState text={describeError(trips.error)} onRetry={trips.refresh} />
      ) : (
        <LoadingState text="Loading the trip…" />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { padding: spacing.lg, paddingBottom: spacing.xxl },
});
