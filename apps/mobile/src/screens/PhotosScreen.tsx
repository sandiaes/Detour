import type { Trip } from "@detour/shared";
import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { call } from "../api/unwrap";
import {
  ListRow,
  Notice,
  RowGroup,
  ScreenHeader,
  SectionHeader,
  StateView,
} from "../components/ds";
import { openAlbum } from "../components/photos/TripAlbums";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { useAllTripExtras } from "../documents/DocumentsProvider";
import { type TripAlbum, albumSource } from "../documents/extras";
import { shortSpan } from "../domain/trips";
import { layout } from "../theme";

/**
 * Photos across all trips (ADR 031): every album linked to a trip on this phone, by trip. Detour
 * shows no photos itself; an album opens in Google Photos (or the browser). Albums are linked on a
 * trip's Photos tab.
 */
export function PhotosScreen() {
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const extras = useAllTripExtras();
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
          />
        ) : (
          withAlbums.map((trip) => (
            <View key={trip.id} testID={`photos-trip-${trip.id}`}>
              <SectionHeader title={`${trip.title} · ${shortSpan(trip)}`} />
              <RowGroup>
                {(extras[trip.id]?.albums ?? []).map((album) => (
                  <ListRow
                    key={album.id}
                    inset="none"
                    icon="photos"
                    title={album.name}
                    detail={albumSource(album.url)}
                    accessibilityHint="Opens the album outside Detour"
                    testID={`photos-album-${album.id}`}
                    onPress={() => void open(album)}
                    trailing={null}
                  />
                ))}
              </RowGroup>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingHorizontal: layout.gutter, gap: layout.block },
});
