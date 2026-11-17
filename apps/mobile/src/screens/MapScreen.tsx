import type { Trip } from "@detour/shared";
import { Camera, Map, Marker, type CameraRef } from "@maplibre/maplibre-react-native";
import { useEffect, useMemo, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call } from "../api/unwrap";
import { AttributionBar } from "../components/AttributionBar";
import { OfflineMap } from "../components/OfflineMap";
import {
  IconButton,
  MapChip,
  MapFailure,
  PlannedFeature,
  ScreenHeader,
  StopMark,
} from "../components/ds";
import { keys } from "../data/actions";
import { useResource } from "../data/DataProvider";
import { boundsOf } from "../domain/itinerary";
import { type WorldPoint, worldPoints, worldSummary } from "../domain/worldMap";
import { useNavigation } from "../nav/Navigator";
import { TOUCH, border, colors, layout, size as sizes, spacing, type, weight } from "../theme";

const PADDING = { top: 72, right: 56, bottom: 72, left: 56 };

/** The Map tab: a world map of the places the user has been to (green) and is going to (navy). */
export function MapScreen() {
  const nav = useNavigation();
  const { state } = useBackend();
  const trips = useResource<Trip[]>(keys.trips, (client) => call(client.GET("/v1/trips")));
  const points = useMemo(() => worldPoints(trips.data ?? []), [trips.data]);
  const counts = worldSummary(points);
  const bounds = useMemo(() => boundsOf(points), [points]);
  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;

  const camera = useRef<CameraRef>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [interactions, setInteractions] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = points.find((p) => p.id === selectedId) ?? null;

  useEffect(() => {
    if (!bounds || status !== "loaded") return;
    // One point: stay on the world view rather than zooming into a single city.
    if (points.length === 1) {
      camera.current?.flyTo({ center: points[0]!.lngLat, zoom: 4, duration: 400 });
    } else {
      camera.current?.fitBounds(bounds, { padding: PADDING, duration: 400 });
    }
  }, [bounds, points, status]);

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Map" />
      {points.length === 0 && trips.data ? (
        <View style={styles.empty}>
          <PlannedFeature
            icon="map"
            title="No places yet"
            text="The cities of your trips appear here: green for where you have been, navy for where you are going."
            testID="map-empty"
          />
        </View>
      ) : !mapConfig ? (
        <OfflineMap />
      ) : (
        <>
          <View style={[styles.fill, styles.clip]}>
            <Map
              key={attempt}
              style={styles.fill}
              mapStyle={mapConfig.style_url}
              logo={false}
              attribution={false}
              onDidFinishLoadingMap={() => setStatus("loaded")}
              onDidFailLoadingMap={() => setStatus("failed")}
              onRegionWillChange={(e) => {
                if (e.nativeEvent.userInteraction) setInteractions((n) => n + 1);
              }}
            >
              <Camera ref={camera} initialViewState={{ center: [10, 25], zoom: 1 }} />
              {points.map((p) => (
                <Marker
                  key={p.id}
                  id={p.id}
                  lngLat={p.lngLat}
                  anchor="center"
                  selected={selectedId === p.id}
                  onPress={() => setSelectedId(p.id)}
                >
                  <View
                    accessible
                    accessibilityRole="button"
                    accessibilityLabel={`${p.state === "been" ? "Been to" : "Going to"} ${p.name}`}
                    accessibilityHint="Shows the trips"
                    accessibilityState={{ selected: selectedId === p.id }}
                    style={styles.hit}
                  >
                    <StopMark
                      kind={p.state === "been" ? "sight" : "city"}
                      icon={p.state === "going" ? "city" : undefined}
                      size="map"
                      selected={selectedId === p.id}
                    />
                  </View>
                </Marker>
              ))}
            </Map>
            {status === "failed" ? (
              <MapFailure
                message="The map could not load. This happens without a connection or when the map host is down."
                onRetry={() => {
                  setStatus("loading");
                  setAttempt((n) => n + 1);
                }}
                listLabel="Show trips"
                onShowList={() => nav.switchRoot({ name: "trips" })}
              />
            ) : null}
            {status === "loading" ? <MapChip text="Loading the map…" live /> : null}
            <AttributionBar lines={mapConfig.attribution} userInteractionCount={interactions} />
          </View>
          <Panel selected={selected} counts={counts} onClose={() => setSelectedId(null)} />
        </>
      )}
    </View>
  );
}

function Panel({
  selected,
  counts,
  onClose,
}: {
  selected: WorldPoint | null;
  counts: { been: number; going: number };
  onClose: () => void;
}) {
  const nav = useNavigation();
  return (
    <View style={styles.panel} accessibilityLiveRegion="polite">
      {selected ? (
        <View style={styles.selectedRow}>
          <View style={styles.selectedText}>
            <Text style={styles.title} numberOfLines={2}>
              {selected.name}
            </Text>
            <Text style={styles.meta}>
              {selected.state === "been" ? "Been" : "Going"} ·{" "}
              {selected.trips.map((t) => t.title).join(", ")}
            </Text>
          </View>
          <IconButton
            icon="chevronRight"
            label={`Open ${selected.trips[0]!.title}`}
            size="sm"
            color={colors.muted}
            onPress={() => nav.push({ name: "tripOverview", tripId: selected.trips[0]!.id })}
          />
          <IconButton
            icon="close"
            label="Close details"
            size="sm"
            color={colors.muted}
            onPress={onClose}
          />
        </View>
      ) : (
        <View style={styles.key} accessible accessibilityLabel={keyText(counts)}>
          <View style={styles.keyItem}>
            <StopMark kind="sight" size="key" />
            <Text style={styles.meta}>Been · {counts.been}</Text>
          </View>
          <View style={styles.keyItem}>
            <StopMark kind="city" icon="city" size="key" />
            <Text style={styles.meta}>Going · {counts.going}</Text>
          </View>
        </View>
      )}
    </View>
  );
}

function keyText(c: { been: number; going: number }): string {
  return `${c.been} places been to, ${c.going} places going to`;
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  clip: { overflow: "hidden" },
  empty: { flex: 1, paddingHorizontal: layout.gutter },
  hit: {
    width: TOUCH,
    height: TOUCH,
    minHeight: TOUCH,
    alignItems: "center",
    justifyContent: "center",
  },
  panel: {
    backgroundColor: colors.background,
    borderTopWidth: border.hairline,
    borderTopColor: colors.border,
    paddingHorizontal: layout.gutter,
    paddingVertical: spacing.md,
    minHeight: sizes.tile + 2 * spacing.md,
    justifyContent: "center",
  },
  title: { ...type.label, fontWeight: weight.bold, color: colors.text },
  meta: { ...type.caption, color: colors.muted },
  selectedRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  selectedText: { flex: 1, gap: spacing.xxs },
  key: { flexDirection: "row", gap: spacing.lg, alignItems: "center" },
  keyItem: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
});
