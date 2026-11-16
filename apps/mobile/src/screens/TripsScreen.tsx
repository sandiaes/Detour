import type { Trip } from "@detour/shared";
import { useState } from "react";
import { FlatList, Image, RefreshControl, StyleSheet, Text, View } from "react-native";

import { call, describeError, isOfflineError } from "../api/unwrap";
import {
  Badge,
  type BadgeTone,
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Tabs,
  WakingServer,
  useAnnounceOnMount,
  FocusPressable,
} from "../components/ds";
import { Cover } from "../components/ds/Cover";
import { ResourceNotices } from "../components/ResourceNotices";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useAllTripExtras } from "../documents/DocumentsProvider";
import {
  TRIP_PHASE_LABEL,
  type TripPhase,
  type TripTab,
  shortSpan,
  tripPhase,
  tripsInTab,
} from "../domain/trips";
import { type Route, useNavigation } from "../nav/Navigator";
import {
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

/** A past trip opens on its map of visited places (ADR 006); every other trip on its overview,
 * which shows the active plan or leads to the proposals (ADR 021). */
export function tripRoute(trip: Trip): Route {
  if (trip.status === "past") return { name: "pastTrip", tripId: trip.id };
  return { name: "tripOverview", tripId: trip.id };
}

const PHASE_TONE: Record<TripPhase, BadgeTone> = {
  planning: "onImage",
  upcoming: "primary",
  inProgress: "accent",
  past: "onImage",
};

const CARD_HEIGHT = 168;

/** The cover with the trip's name, dates and length on it, bottom left, and the status at the top
 * right (docs/design.md): nothing else. */
export function TripCard({
  trip,
  onPress,
  localCoverUri = null,
}: {
  trip: Trip;
  onPress: () => void;
  /** A cover chosen from the phone (ADR 031), shown instead of the destination's photo. */
  localCoverUri?: string | null;
}) {
  const phase = tripPhase(trip);
  const label = TRIP_PHASE_LABEL[phase];
  const span = shortSpan(trip);
  return (
    <FocusPressable
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
        uri={localCoverUri}
        height={CARD_HEIGHT}
        rounded={radius.lg}
        scrim
      >
        <View style={styles.cardBadge}>
          <Badge label={label} tone={PHASE_TONE[phase]} />
        </View>
        <View style={styles.cardText} pointerEvents="none">
          <Text style={styles.cardTitle} numberOfLines={2}>
            {trip.title}
          </Text>
          <Text style={styles.cardMeta} numberOfLines={1}>
            {span}
          </Text>
        </View>
      </Cover>
    </FocusPressable>
  );
}

const EMPTY_TEXT: Record<TripTab, { title: string; text: string }> = {
  upcoming: {
    title: "No upcoming trips",
    text: "Start a trip for any place, then add sights, restaurants and documents. Detour can also suggest itineraries.",
  },
  past: {
    title: "No past trips yet",
    text: "A trip moves here two days after its last day, or when you mark it as past in the trip's menu.",
  },
};

// The logo's wordmark alone, "Detour" and the orange dot, on a transparent ground
// (assets/detour-wordmark.png, cut from docs/brand/detour-logo.png).
const LOGO = require("../../assets/detour-wordmark.png") as number;
const LOGO_HEIGHT = 31;
const LOGO_WIDTH = Math.round((LOGO_HEIGHT * 774) / 184);

export function TripsScreen() {
  const nav = useNavigation();
  const titleRef = useAnnounceOnMount();
  const trips = useResource<Trip[]>(keys.trips, (client) => call(client.GET("/v1/trips")));
  const extras = useAllTripExtras();
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
          text="Start a trip for any place, then add sights, restaurants and documents. Detour can also suggest itineraries."
          action={{
            label: "New trip",
            icon: "add",
            variant: "primary",
            fill: true,
            onPress: create,
          }}
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
            <TripCard
              trip={item}
              localCoverUri={extras[item.id]?.cover?.uri ?? null}
              onPress={() => nav.push(tripRoute(item))}
            />
          )}
          ListHeaderComponent={<ResourceNotices resource={trips} noun="trips" />}
          ListEmptyComponent={<EmptyState layout="inline" title={empty.title} text={empty.text} />}
          ListFooterComponent={
            tab === "upcoming" ? (
              <Button label="New trip" icon="add" fill onPress={create} />
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
      <View
        ref={titleRef}
        style={styles.brand}
        accessible
        accessibilityRole="header"
        accessibilityLabel="Detour"
      >
        <Image
          source={LOGO}
          style={{ width: LOGO_WIDTH, height: LOGO_HEIGHT }}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
          testID="detour-logo"
        />
      </View>
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  brand: { paddingHorizontal: layout.gutter, paddingTop: spacing.sm, paddingBottom: spacing.xs },
  list: { padding: layout.gutter, gap: spacing.lg },
  card: { minHeight: sizes.rowCompact },
  pressed: { opacity: opacity.pressed },
  cardBadge: { position: "absolute", top: spacing.md, right: spacing.md },
  // The name, dates and length sit on the photo, bottom left, over the cover's soft gradient;
  // the right is left to the photo credit's "i".
  cardText: {
    position: "absolute",
    left: spacing.md,
    right: spacing.xxl,
    bottom: spacing.md,
    gap: spacing.xxs,
  },
  cardTitle: { ...type.headline, fontWeight: weight.bold, ...textOnImage },
  cardMeta: { ...type.caption, fontWeight: weight.medium, ...textOnImage },
});
