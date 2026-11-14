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
import { Pressable, StyleSheet, Text, View } from "react-native";

import { useProgressiveCount } from "../data/useProgressive";
import {
  STOP_KIND_LABEL,
  boundsOf,
  isEatKind,
  mapPoints,
  transferFeatures,
  transportFeature,
  transportPoint,
} from "../domain/itinerary";
import { colors, radius, shadow, spacing, type } from "../theme";
import { formatSeconds } from "../util/format";
import { AttributionBar } from "./AttributionBar";
import { Button } from "./Button";
import { Icon } from "./ds/Icon";
import { Notice } from "./ui";

/** The touch target of a marker; the drawn marker inside it is smaller (docs/design.md). */
export const MARKER_SIZE = 48;
const DOT = 26;
const DOT_SELECTED = 34;

const PADDING = { top: 56, right: 48, bottom: 48, left: 48 };

type Props = {
  day: Day;
  /** The day before, for the leg from the previous base city (area trips). */
  previousDay?: Day;
  map: ClientConfig["map"];
  /** Opens the day list; offered when the map cannot load. */
  onShowList: () => void;
  /** The highlighted stop (an item id, or the transport marker's id); shared with the list. */
  selectedId: string | null;
  onSelect: (id: string) => void;
};

/**
 * One day on the map (ADR 015, redesigned in ADR 021): numbered stops (sights round and teal,
 * places to eat square and orange), the arrival at a new base city as a transport marker, and
 * straight lines between them. The selection is held by the screen, so the list and the map
 * highlight the same stop.
 */
export function ItineraryMap({ day, previousDay, map, onShowList, selectedId, onSelect }: Props) {
  const points = useMemo(() => mapPoints(day), [day]);
  const transport = useMemo(() => transportPoint(day, previousDay), [day, previousDay]);
  const features = useMemo(() => transferFeatures(day), [day]);
  const bounds = useMemo(
    () => boundsOf(transport ? [...points, transport] : points),
    [points, transport],
  );
  const shownCount = useProgressiveCount(points.length, day.id);
  const shown = points.slice(0, shownCount);
  const shownIds = useMemo(() => new Set(shown.map((p) => p.id)), [shown]);
  // A line appears once both of its stops are on the map.
  const lines = useMemo(() => {
    const leg = transport ? transportFeature(transport) : null;
    return {
      type: "FeatureCollection" as const,
      features: [
        ...features.filter((f) => {
          const [a, b] = f.id.split(">");
          return shownIds.has(a as string) && shownIds.has(b as string);
        }),
        ...(leg ? [leg] : []),
      ],
    };
  }, [features, shownIds, transport]);

  const camera = useRef<CameraRef>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [interactions, setInteractions] = useState(0);
  const [keyOpen, setKeyOpen] = useState(false);

  // Another day: fit the camera to its stops.
  useEffect(() => {
    if (!bounds || status !== "loaded") return;
    camera.current?.fitBounds(bounds, { padding: PADDING, duration: 400 });
  }, [day.id, bounds, status]);

  // A stop chosen in the list: bring it into view.
  useEffect(() => {
    if (!selectedId || status !== "loaded") return;
    const target =
      points.find((p) => p.id === selectedId)?.lngLat ??
      (transport?.id === selectedId ? transport.lngLat : null);
    if (target) camera.current?.easeTo({ center: target, duration: 350 });
  }, [selectedId, status, points, transport]);

  const initial = bounds
    ? bounds[0] === bounds[2] && bounds[1] === bounds[3]
      ? { center: [bounds[0], bounds[1]] as [number, number], zoom: 14 }
      : { bounds, padding: PADDING }
    : { center: [0, 20] as [number, number], zoom: 1 };

  return (
    <View style={[styles.fill, styles.clip]}>
      <Map
        key={attempt}
        style={[styles.fill, styles.clip]}
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
            style={{ lineColor: colors.outline, lineWidth: 2 }}
          />
          <Layer
            id="transfers-estimated"
            type="line"
            filter={["==", ["get", "confidence"], "estimated"]}
            style={{ lineColor: colors.outline, lineWidth: 2, lineDasharray: [2, 2] }}
          />
        </GeoJSONSource>
        {transport ? (
          <Marker
            key={transport.id}
            id={transport.id}
            lngLat={transport.lngLat}
            anchor="center"
            selected={selectedId === transport.id}
            onPress={() => onSelect(transport.id)}
          >
            <View
              accessible
              accessibilityRole="button"
              accessibilityLabel={`Transport: ${transport.arrival.mode === "walk" ? "walk" : "drive"} to ${transport.name}${transport.fromName ? ` from ${transport.fromName}` : ""}, ${formatSeconds(transport.arrival.seconds)}, ${transport.arrival.confidence}`}
              accessibilityHint="Highlights it in the list"
              accessibilityState={{ selected: selectedId === transport.id }}
              style={styles.hit}
            >
              <View
                style={[
                  styles.dot,
                  styles.dotTransport,
                  selectedId === transport.id && styles.dotSelected,
                ]}
              >
                <Icon name="transport" size={14} color={colors.onPrimary} />
              </View>
            </View>
          </Marker>
        ) : null}
        {shown.map((p) => {
          const isSelected = selectedId === p.id;
          return (
            <Marker
              key={p.id}
              id={p.id}
              lngLat={p.lngLat}
              anchor="center"
              selected={isSelected}
              onPress={() => onSelect(p.id)}
            >
              <View
                accessible
                accessibilityRole="button"
                accessibilityLabel={`Stop ${p.ordinal}, ${STOP_KIND_LABEL[p.kind]}: ${p.name}`}
                accessibilityHint="Highlights it in the list"
                accessibilityState={{ selected: isSelected }}
                style={styles.hit}
              >
                <View
                  style={[
                    styles.dot,
                    isEatKind(p.kind) && styles.dotEat,
                    isSelected && styles.dotSelected,
                  ]}
                >
                  <Text style={styles.dotText} maxFontSizeMultiplier={1.3}>
                    {p.ordinal}
                  </Text>
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
            The map could not load. This happens without a connection or when the map host is down.
            The day list still works.
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
      {points.length === 0 && !transport ? (
        <View style={styles.loadingTag}>
          <Text style={styles.loadingText}>Nothing is planned on this day.</Text>
        </View>
      ) : null}

      <View style={styles.keyCorner}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Map key"
          accessibilityState={{ expanded: keyOpen }}
          onPress={() => setKeyOpen((o) => !o)}
          hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
          style={styles.keyButton}
          testID="map-key"
        >
          <Icon name={keyOpen ? "close" : "list"} size={18} />
        </Pressable>
        {keyOpen ? <Legend /> : null}
      </View>

      {/* The sheet of stops curves over the map's lower edge: lift the credit above the curve. */}
      <AttributionBar
        lines={map.attribution}
        userInteractionCount={interactions}
        bottomOffset={radius.lg + spacing.xs}
      />
    </View>
  );
}

export function Legend() {
  return (
    <View style={styles.legend} accessibilityLiveRegion="polite">
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <View style={[styles.keyMarker, styles.keySight]} />
        </View>
        <Text style={styles.legendText}>Attraction</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <View style={[styles.keyMarker, styles.keyEat]} />
        </View>
        <Text style={styles.legendText}>Restaurant or café</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <View style={[styles.keyMarker, styles.keyTransport]} />
        </View>
        <Text style={styles.legendText}>Travel to a new base city</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <View style={styles.swatch} />
        </View>
        <Text style={styles.legendText}>Direct line between stops; dashed if estimated</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  clip: { overflow: "hidden" },
  hit: { width: MARKER_SIZE, height: MARKER_SIZE, alignItems: "center", justifyContent: "center" },
  // Small flat discs with a thin white edge: sights round and teal, places to eat square-ish and
  // orange, travel navy. The selected stop is larger and navy. No heavy rings.
  dot: {
    width: DOT,
    height: DOT,
    borderRadius: DOT / 2,
    backgroundColor: colors.marker,
    borderWidth: 2,
    borderColor: colors.onPrimary,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  dotEat: { backgroundColor: colors.eat, borderRadius: 8 },
  dotTransport: { backgroundColor: colors.ink, borderRadius: 8 },
  dotSelected: {
    width: DOT_SELECTED,
    height: DOT_SELECTED,
    borderRadius: DOT_SELECTED / 2,
    backgroundColor: colors.markerSelected,
  },
  dotText: { color: colors.onPrimary, fontWeight: "600", fontSize: 12 },
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
    top: spacing.sm,
    left: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.94)",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  loadingText: { ...type.caption, color: colors.text },
  keyCorner: {
    position: "absolute",
    top: spacing.sm,
    right: spacing.sm,
    alignItems: "flex-end",
    gap: spacing.sm,
    maxWidth: 270,
  },
  // A small flat button: 36 dp drawn, 48 dp to touch (hit slop).
  keyButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  legend: {
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    ...shadow.card,
  },
  // Every key sits in the same 20 dp column, so the words line up.
  legendRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 20 },
  legendKey: { width: 20, alignItems: "center", justifyContent: "center" },
  keyMarker: { width: 14, height: 14 },
  keySight: { backgroundColor: colors.marker, borderRadius: 7 },
  keyEat: { backgroundColor: colors.eat, borderRadius: 4 },
  keyTransport: { backgroundColor: colors.ink, borderRadius: 4 },
  legendText: { ...type.caption, color: colors.text, flexShrink: 1 },
  swatch: { width: 20, height: 0, borderTopWidth: 2, borderColor: colors.outline },
});
