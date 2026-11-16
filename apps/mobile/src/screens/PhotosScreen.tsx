import type { Trip } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { call } from "../api/unwrap";
import {
  Button,
  Card,
  FocusPressable,
  Icon,
  ListRow,
  Notice,
  RowGroup,
  ScreenHeader,
  StateView,
  Tile,
} from "../components/ds";
import { Cover } from "../components/ds/Cover";
import { openAlbum } from "../components/photos/TripAlbums";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useAllTripExtras, useSyncTrips } from "../documents/DocumentsProvider";
import { type TripAlbum, albumSource } from "../documents/extras";
import { shortSpan } from "../domain/trips";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, radius, size as sizes, spacing, type } from "../theme";

/**
 * Photos across all trips (ADR 031): every album linked to a trip on this phone, by trip. Detour
 * shows no photos itself; an album opens in Google Photos (or the browser). Albums are linked on a
 * trip's Photos tab.
 */
export function PhotosScreen() {
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const extras = useAllTripExtras();
  // Albums and covers are shared on the server (ADR 034, step 5): keep this phone's copy current.
  useSyncTrips(trips.data);
  const nav = useNavigation();
  const [problem, setProblem] = useState<string | null>(null);
  const withAlbums = (trips.data ?? []).filter((t) => (extras[t.id]?.albums.length ?? 0) > 0);

  const open = async (album: TripAlbum) => {
    setProblem(null);
    try {
      await openAlbum(album);
    } catch {
      setProblem("This phone could not open the album's link. Check the link on the trip.");
    }
  };

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Photos" />
      <ScrollView contentContainerStyle={styles.content}>
        {problem ? <Notice tone="error">{problem}</Notice> : null}
        {withAlbums.length === 0 ? (
          <StateView
            kind="empty"
            layout="inline"
            icon="photos"
            title="No albums linked yet"
            text="Open a trip and link its Google Photos album on the trip's Photos tab. Your albums will be listed here, by trip."
            testID="photos-empty"
          >
            <Button
              label="Go to my trips"
              fill
              testID="photos-go-trips"
              onPress={() => nav.switchRoot({ name: "trips" })}
            />
          </StateView>
        ) : (
          withAlbums.map((trip) => (
            <Card key={trip.id} padded={false} testID={`photos-trip-${trip.id}`}>
              <FocusPressable
                accessibilityRole="button"
                accessibilityLabel={`${trip.title}. ${shortSpan(trip)}`}
                accessibilityHint="Opens the trip's Photos tab"
                onPress={() =>
                  nav.push({ name: "tripOverview", tripId: trip.id, section: "photos" })
                }
                style={({ pressed }) => [styles.tripHead, pressed && styles.pressed]}
                testID={`photos-open-${trip.id}`}
              >
                <View style={styles.thumb}>
                  <Cover
                    seedKey={trip.destination.ref}
                    photo={trip.cover_image}
                    uri={extras[trip.id]?.cover?.uri ?? null}
                    height={sizes.thumb}
                    rounded={radius.md}
                    credit={false}
                  />
                </View>
                <View style={styles.tripText}>
                  <Text style={styles.tripTitle} numberOfLines={2}>
                    {trip.title}
                  </Text>
                  <Text style={styles.tripMeta} numberOfLines={1}>
                    {shortSpan(trip)}
                  </Text>
                </View>
                <Icon name="chevronRight" size="sm" color={colors.muted} />
              </FocusPressable>
              <RowGroup>
                {(extras[trip.id]?.albums ?? []).map((album) => (
                  <ListRow
                    key={album.id}
                    inset="gutter"
                    leading={<Tile icon="photos" fg={colors.primary} bg={colors.selectedSoft} />}
                    title={album.name}
                    detail={albumSource(album.url)}
                    accessibilityHint="Opens the album outside Detour"
                    testID={`photos-album-${album.id}`}
                    onPress={() => void open(album)}
                    trailing={<Icon name="external" size="sm" color={colors.muted} />}
                  />
                ))}
              </RowGroup>
            </Card>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingHorizontal: layout.gutter, gap: layout.block, paddingBottom: spacing.xxl },
  tripHead: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
  },
  pressed: { backgroundColor: colors.surfaceMuted },
  thumb: { width: sizes.thumb, height: sizes.thumb },
  tripText: { flex: 1, gap: spacing.xxs },
  tripTitle: { ...type.cardTitle, color: colors.text },
  tripMeta: { ...type.caption, color: colors.muted },
});
