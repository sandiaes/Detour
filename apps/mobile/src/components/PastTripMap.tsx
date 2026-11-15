import type { ClientConfig } from "@detour/shared";
import { Camera, Map, Marker, type CameraRef } from "@maplibre/maplibre-react-native";
import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useProgressiveCount } from "../data/useProgressive";
import { type PastPoint, VISIT_KIND_LABEL, dayColor } from "../domain/pastTrip";
import { boundsOf } from "../domain/itinerary";
import { TOUCH, border, colors, layout, size as sizes, spacing, type, weight } from "../theme";
import { AttributionBar } from "./AttributionBar";
import { IconButton, MapChip, MapFailure, StopMark, Tile } from "./ds";

const PADDING = { top: 72, right: 56, bottom: 72, left: 56 };
/** Android's minimum touch target; the markers are drawn smaller inside it. */

type Props = {
  points: PastPoint[];
  map: ClientConfig["map"];
  /** Opens the list; offered when the map cannot load. */
  onShowList: () => void;
};

/** The visited cities and attractions of a past trip. Markers only: a past trip keeps no routes
 * or travel times (ADR 006), so there is no line layer. */
export function PastTripMap({ points, map, onShowList }: Props) {
  const bounds = useMemo(() => boundsOf(points), [points]);
  const resetKey = useMemo(() => points.map((p) => p.id).join(","), [points]);
  const shownCount = useProgressiveCount(points.length, resetKey);
  const shown = points.slice(0, shownCount);

  const camera = useRef<CameraRef>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [interactions, setInteractions] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const dayList = useMemo(
    () =>
      [...new Set(points.filter((p) => p.kind !== "city").map((p) => p.day))].sort((a, b) => a - b),
    [points],
  );
  const selected = points.find((p) => p.id === selectedId) ?? null;

  // Visits were cleared or restored: fit the camera to what is shown.
  useEffect(() => {
    if (!bounds || status !== "loaded") return;
    camera.current?.fitBounds(bounds, { padding: PADDING, duration: 400 });
  }, [bounds, status]);

  const initial = bounds
    ? points.length === 1
      ? { center: points[0]!.lngLat, zoom: 12 }
      : { bounds, padding: PADDING }
    : { center: [0, 20] as [number, number], zoom: 1 };

  return (
    <View style={styles.fill}>
      <View style={[styles.fill, styles.clip]}>
        <Map
          key={attempt}
          style={styles.fill}
          mapStyle={map.style_url}
          logo={false}
          attribution={false}
          onDidFinishLoadingMap={() => setStatus("loaded")}
          onDidFailLoadingMap={() => setStatus("failed")}
          // Only a user gesture collapses the credit; the map's own camera moves do not.
          onRegionWillChange={(e) => {
            if (e.nativeEvent.userInteraction) setInteractions((n) => n + 1);
          }}
        >
          <Camera ref={camera} initialViewState={initial} />
          {shown.map((p) => {
            const isCity = p.kind === "city";
            return (
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
                  accessibilityLabel={`${VISIT_KIND_LABEL[p.kind]}, day ${p.day}: ${p.name}`}
                  accessibilityHint="Shows details"
                  accessibilityState={{ selected: selectedId === p.id }}
                  style={styles.hit}
                >
                  <StopMark
                    kind={isCity ? "city" : "sight"}
                    icon={isCity ? "city" : undefined}
                    color={isCity ? undefined : dayColor(p.day)}
                    size="map"
                    selected={selectedId === p.id}
                  />
                </View>
              </Marker>
            );
          })}
        </Map>

        {status === "failed" ? (
          <MapFailure
            message="The map could not load. This happens without a connection or when the map host is down. The list still works."
            onRetry={() => {
              setStatus("loading");
              setAttempt((n) => n + 1);
            }}
            listLabel="Show the list"
            onShowList={onShowList}
          />
        ) : null}
        {status === "loading" ? <MapChip text="Loading the map…" live /> : null}
        {points.length > shownCount ? (
          <MapChip text={`Placing visits ${shownCount} of ${points.length}…`} />
        ) : null}

        <AttributionBar lines={map.attribution} userInteractionCount={interactions} />
      </View>

      <View style={styles.panel} accessibilityLiveRegion="polite">
        {selected ? (
          <View style={styles.selectedRow}>
            <Tile
              icon={selected.kind === "city" ? "city" : "sight"}
              fg={colors.onPrimary}
              bg={selected.kind === "city" ? colors.ink : dayColor(selected.day)}
            />
            <View style={styles.selectedText}>
              <Text style={styles.title} numberOfLines={2}>
                {selected.name}
              </Text>
              <Text style={styles.meta}>
                {VISIT_KIND_LABEL[selected.kind]} · Day {selected.day}
              </Text>
            </View>
            <IconButton
              icon="close"
              label="Close details"
              size="sm"
              color={colors.muted}
              onPress={() => setSelectedId(null)}
            />
          </View>
        ) : (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.days}
            accessibilityLabel="Colours by day"
          >
            {dayList.map((d) => (
              <View key={d} style={styles.dayChip} accessible accessibilityLabel={`Day ${d}`}>
                <StopMark kind="sight" size="key" color={dayColor(d)} />
                <Text style={styles.legendText}>Day {d}</Text>
              </View>
            ))}
          </ScrollView>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  clip: { overflow: "hidden" },
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
  days: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  dayChip: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  legendText: { ...type.caption, color: colors.muted, flexShrink: 1 },
});
