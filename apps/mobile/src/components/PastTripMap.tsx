import type { ClientConfig } from "@detour/shared";
import { Camera, Map, Marker, type CameraRef } from "@maplibre/maplibre-react-native";
import { useEffect, useMemo, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useProgressiveCount } from "../data/useProgressive";
import { type PastPoint, VISIT_KIND_LABEL } from "../domain/pastTrip";
import { boundsOf } from "../domain/itinerary";
import { colors, radius, spacing, type } from "../theme";
import { AttributionBar } from "./AttributionBar";
import { Button } from "./Button";
import { Notice } from "./ui";

const PADDING = { top: 72, right: 56, bottom: 72, left: 56 };
const CITY_SIZE = 44;
const ATTRACTION_SIZE = 32;
/** Android's minimum touch target; the markers are drawn smaller inside it. */
const TOUCH_SIZE = 48;

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
      <View style={styles.fill}>
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
                  <View
                    style={[
                      isCity ? styles.city : styles.attraction,
                      selectedId === p.id && styles.selected,
                    ]}
                  >
                    {isCity ? (
                      <Text style={styles.cityText} maxFontSizeMultiplier={1.3}>
                        C
                      </Text>
                    ) : null}
                  </View>
                </View>
              </Marker>
            );
          })}
        </Map>

        {status === "failed" ? (
          <View style={styles.failure}>
            <Notice
              tone="error"
              action={{
                label: "Try the map again",
                onPress: () => {
                  setStatus("loading");
                  setAttempt((n) => n + 1);
                },
              }}
            >
              The map could not load. This happens without a connection or when the map host is
              down. The list still works.
            </Notice>
            <Button label="Show the list" variant="secondary" onPress={onShowList} />
          </View>
        ) : null}
        {status === "loading" ? (
          <View style={styles.tag} accessibilityLiveRegion="polite">
            <Text style={styles.tagText}>Loading the map…</Text>
          </View>
        ) : null}
        {points.length > shownCount ? (
          <View style={styles.tag}>
            <Text style={styles.tagText}>
              Placing visits {shownCount} of {points.length}…
            </Text>
          </View>
        ) : null}

        <AttributionBar lines={map.attribution} userInteractionCount={interactions} />
      </View>

      <View style={styles.panel} accessibilityLiveRegion="polite">
        {selected ? (
          <>
            <Text style={styles.title}>{selected.name}</Text>
            <Text style={styles.meta}>
              {VISIT_KIND_LABEL[selected.kind]} · day {selected.day}
            </Text>
          </>
        ) : (
          <View style={styles.legend}>
            <Text style={styles.meta}>Tap a marker for details.</Text>
            <View style={styles.legendRow}>
              <View style={[styles.city, styles.key]}>
                <Text style={styles.cityText}>C</Text>
              </View>
              <Text style={styles.legendText}>Square, blue: city</Text>
            </View>
            <View style={styles.legendRow}>
              <View style={[styles.attraction, styles.key]} />
              <Text style={styles.legendText}>Round, green: attraction</Text>
            </View>
            <Text style={styles.legendText}>
              Past trips keep the places, not the routes or travel times.
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  hit: {
    width: TOUCH_SIZE,
    height: TOUCH_SIZE,
    minHeight: TOUCH_SIZE,
    alignItems: "center",
    justifyContent: "center",
  },
  city: {
    width: CITY_SIZE,
    height: CITY_SIZE,
    borderRadius: radius.sm,
    backgroundColor: colors.link,
    borderWidth: 3,
    borderColor: colors.onPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  cityText: { color: colors.onPrimary, fontWeight: "700", fontSize: 16 },
  attraction: {
    width: ATTRACTION_SIZE,
    height: ATTRACTION_SIZE,
    borderRadius: ATTRACTION_SIZE / 2,
    backgroundColor: colors.marker,
    borderWidth: 3,
    borderColor: colors.onPrimary,
  },
  selected: { backgroundColor: colors.markerSelected, borderColor: colors.warning },
  key: { width: 20, height: 20, borderWidth: 2 },
  failure: {
    position: "absolute",
    top: spacing.md,
    left: 0,
    right: 0,
    gap: spacing.sm,
    alignItems: "flex-start",
  },
  tag: {
    position: "absolute",
    top: spacing.md,
    right: spacing.md,
    backgroundColor: "rgba(255,255,255,0.92)",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  tagText: { ...type.caption, color: colors.text },
  panel: {
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    padding: spacing.lg,
    gap: spacing.xs,
  },
  title: { ...type.heading, color: colors.text },
  meta: { ...type.small, color: colors.muted },
  legend: { gap: spacing.xs },
  legendRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  legendText: { ...type.caption, color: colors.muted, flexShrink: 1 },
});
