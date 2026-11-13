import type { ClientConfig, Day } from "@detour/shared";
import {
  Camera,
  GeoJSONSource,
  Layer,
  Map,
  Marker,
  type CameraRef,
} from "@maplibre/maplibre-react-native";
import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useProgressiveCount } from "../data/useProgressive";
import { type MapPoint, boundsOf, mapPoints, transferFeatures } from "../domain/itinerary";
import { colors, radius, spacing, type } from "../theme";
import { formatMinutes, formatSeconds } from "../util/format";
import { AttributionBar } from "./AttributionBar";
import { Button } from "./Button";
import { Notice } from "./ui";

export const MARKER_SIZE = 48;
const PADDING = { top: 72, right: 56, bottom: 72, left: 56 };

type Props = {
  day: Day;
  map: ClientConfig["map"];
  /** Opens the day list; offered when the map cannot load. */
  onShowList: () => void;
};

export function ItineraryMap({ day, map, onShowList }: Props) {
  const points = useMemo(() => mapPoints(day), [day]);
  const features = useMemo(() => transferFeatures(day), [day]);
  const bounds = useMemo(() => boundsOf(points), [points]);
  const shownCount = useProgressiveCount(points.length, day.id);
  const shown = points.slice(0, shownCount);
  const shownIds = useMemo(() => new Set(shown.map((p) => p.id)), [shown]);
  // A line appears once both of its stops are on the map.
  const lines = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: features.filter((f) => {
        const [a, b] = f.id.split(">");
        return shownIds.has(a as string) && shownIds.has(b as string);
      }),
    }),
    [features, shownIds],
  );

  const camera = useRef<CameraRef>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [interactions, setInteractions] = useState(0);
  // The selection belongs to one day; another day starts with nothing selected.
  const [selection, setSelection] = useState<{ dayId: string; pointId: string } | null>(null);
  const selected =
    (selection?.dayId === day.id && points.find((p) => p.id === selection.pointId)) || null;
  const setSelected = (p: MapPoint) => setSelection({ dayId: day.id, pointId: p.id });

  // Another day: fit the camera to its stops.
  useEffect(() => {
    if (!bounds || status !== "loaded") return;
    camera.current?.fitBounds(bounds, { padding: PADDING, duration: 400 });
  }, [day.id, bounds, status]);

  const initial = bounds
    ? points.length === 1
      ? { center: points[0]!.lngLat, zoom: 14 }
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
          <GeoJSONSource id="transfers" data={lines}>
            <Layer
              id="transfers-routed"
              type="line"
              filter={["==", ["get", "confidence"], "routed"]}
              style={{ lineColor: colors.markerSelected, lineWidth: 3 }}
            />
            <Layer
              id="transfers-estimated"
              type="line"
              filter={["==", ["get", "confidence"], "estimated"]}
              style={{ lineColor: colors.markerSelected, lineWidth: 3, lineDasharray: [1.5, 1.5] }}
            />
          </GeoJSONSource>
          {shown.map((p) => (
            <Marker
              key={p.id}
              id={p.id}
              lngLat={p.lngLat}
              anchor="center"
              selected={selected?.id === p.id}
              onPress={() => setSelected(p)}
            >
              <View
                accessible
                accessibilityRole="button"
                accessibilityLabel={`Stop ${p.ordinal}: ${p.name}`}
                accessibilityHint="Shows details"
                accessibilityState={{ selected: selected?.id === p.id }}
                style={[styles.marker, selected?.id === p.id && styles.markerSelected]}
              >
                <Text style={styles.markerText} maxFontSizeMultiplier={1.3}>
                  {p.ordinal}
                </Text>
              </View>
            </Marker>
          ))}
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
              down. The day list still works.
            </Notice>
            <Button label="Show the day list" variant="secondary" onPress={onShowList} />
          </View>
        ) : null}
        {status === "loading" ? (
          <View style={styles.loadingTag} accessibilityLiveRegion="polite">
            <Text style={styles.loadingText}>Loading the map…</Text>
          </View>
        ) : null}
        {points.length > shownCount ? (
          <View style={styles.loadingTag}>
            <Text style={styles.loadingText}>
              Placing stops {shownCount} of {points.length}…
            </Text>
          </View>
        ) : null}

        <AttributionBar lines={map.attribution} userInteractionCount={interactions} />
      </View>

      <View style={styles.panel}>
        {selected ? <StopDetails point={selected} /> : <Legend hasStops={points.length > 0} />}
      </View>
    </View>
  );
}

function StopDetails({ point }: { point: MapPoint }) {
  const { item } = point;
  const time = item.start_time ? item.start_time.slice(0, 5) : "Time not set";
  return (
    <ScrollView style={styles.details} accessibilityLiveRegion="polite">
      <Text style={styles.detailTitle}>
        {point.ordinal}. {point.name}
      </Text>
      <Text style={styles.detailMeta}>
        {time} · {formatMinutes(item.duration_minutes)}
        {item.duration_source === "user" ? " (set by you)" : " (typical visit length)"}
      </Text>
      {item.transfer ? (
        <Text style={styles.detailMeta}>
          Next: {item.transfer.mode === "walk" ? "walk" : "drive"}{" "}
          {formatSeconds(item.transfer.seconds)}, {item.transfer.confidence}
        </Text>
      ) : null}
      {item.reason_texts.map((t) => (
        <Text key={t} style={styles.detailReason}>
          {t}
        </Text>
      ))}
    </ScrollView>
  );
}

function Legend({ hasStops }: { hasStops: boolean }) {
  return (
    <View style={styles.legend}>
      <Text style={styles.detailMeta}>
        {hasStops ? "Tap a numbered stop for details. " : "Nothing is planned on this day. "}
      </Text>
      <View style={styles.legendRow}>
        <View style={[styles.swatch, styles.swatchSolid]} />
        <Text style={styles.legendText}>Solid line: travel time routed</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={[styles.swatch, styles.swatchDashed]} />
        <Text style={styles.legendText}>Dashed line: travel time estimated</Text>
      </View>
      <Text style={styles.legendText}>
        Lines join the stops directly; they are not the road path.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  marker: {
    width: MARKER_SIZE,
    height: MARKER_SIZE,
    borderRadius: MARKER_SIZE / 2,
    backgroundColor: colors.marker,
    borderWidth: 3,
    borderColor: colors.onPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  markerSelected: { backgroundColor: colors.markerSelected, borderColor: colors.warning },
  markerText: { color: colors.onPrimary, fontWeight: "700", fontSize: 16 },
  failure: {
    position: "absolute",
    top: spacing.md,
    left: 0,
    right: 0,
    gap: spacing.sm,
    alignItems: "flex-start",
  },
  loadingTag: {
    position: "absolute",
    top: spacing.md,
    right: spacing.md,
    backgroundColor: "rgba(255,255,255,0.92)",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  loadingText: { ...type.caption, color: colors.text },
  panel: {
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    padding: spacing.lg,
    maxHeight: 190,
  },
  details: { flexGrow: 0 },
  detailTitle: { ...type.heading, color: colors.text },
  detailMeta: { ...type.small, color: colors.muted },
  detailReason: { ...type.small, color: colors.text, marginTop: spacing.xs },
  legend: { gap: spacing.xs },
  legendRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  legendText: { ...type.caption, color: colors.muted, flexShrink: 1 },
  swatch: { width: 36, height: 0, borderTopWidth: 3, borderColor: colors.markerSelected },
  swatchSolid: { borderStyle: "solid" },
  swatchDashed: { borderStyle: "dashed" },
});
