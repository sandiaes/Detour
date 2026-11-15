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
import { StyleSheet, Text, View } from "react-native";

import { useProgressiveCount } from "../data/useProgressive";
import {
  STOP_KIND_LABEL,
  boundsOf,
  isEatKind,
  mapPoints,
  stayFeature,
  stayPoint,
  transferFeatures,
  transportFeature,
  transportPoint,
} from "../domain/itinerary";
import { TOUCH, border, colors, radius, spacing, type } from "../theme";
import { formatSeconds } from "../util/format";
import { AttributionBar } from "./AttributionBar";
import { IconButton, MapChip, MapFailure, MapPanel, StopMark } from "./ds";

/** The touch target of a marker; the drawn marker inside it is smaller (docs/design.md). */
/** Each marker keeps a 48 dp touch area around the drawn mark. */
export const MARKER_SIZE = TOUCH;

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
  const stay = useMemo(() => stayPoint(day), [day]);
  const bounds = useMemo(
    () => boundsOf([...points, ...(transport ? [transport] : []), ...(stay ? [stay] : [])]),
    [points, transport, stay],
  );
  const shownCount = useProgressiveCount(points.length, day.id);
  const shown = points.slice(0, shownCount);
  const shownIds = useMemo(() => new Set(shown.map((p) => p.id)), [shown]);
  // A line appears once both of its stops are on the map.
  const lines = useMemo(() => {
    const leg = transport ? transportFeature(transport) : null;
    const morning = stayFeature(day);
    return {
      type: "FeatureCollection" as const,
      features: [
        ...(morning && shownIds.has(stay?.start.to_item_id ?? "") ? [morning] : []),
        ...features.filter((f) => {
          const [a, b] = f.id.split(">");
          return shownIds.has(a as string) && shownIds.has(b as string);
        }),
        ...(leg ? [leg] : []),
      ],
    };
  }, [day, features, shownIds, stay, transport]);

  const camera = useRef<CameraRef>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const [interactions, setInteractions] = useState(0);
  const [keyOpen, setKeyOpen] = useState(false);

  // Another day: fit the camera to its stops.
  useEffect(() => {
    if (!bounds || status !== "loaded") return;
    // One stop (or stops on one spot) gives an empty box: fitting it would zoom to the limit, so
    // centre on it at a street-level zoom instead.
    if (bounds[0] === bounds[2] && bounds[1] === bounds[3]) {
      camera.current?.easeTo({ center: [bounds[0], bounds[1]], zoom: 14, duration: 400 });
    } else {
      camera.current?.fitBounds(bounds, { padding: PADDING, duration: 400 });
    }
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
        {stay ? (
          <Marker
            key={stay.id}
            id={stay.id}
            lngLat={stay.lngLat}
            anchor="center"
            selected={false}
            onPress={() => {}}
          >
            <View
              accessible
              accessibilityLabel={`Your stay: ${stay.name}`}
              style={styles.hit}
              testID="stay-marker"
            >
              <StopMark kind="city" icon="home" size="map" />
            </View>
          </Marker>
        ) : null}
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
              accessibilityLabel={
                transport.arrival.seconds === null
                  ? `Transport: travel to ${transport.name}${transport.fromName ? ` from ${transport.fromName}` : ""}, time not calculated`
                  : `Transport: ${transport.arrival.mode === "walk" ? "walk" : "drive"} to ${transport.name}${transport.fromName ? ` from ${transport.fromName}` : ""}, ${formatSeconds(transport.arrival.seconds)}, ${transport.arrival.confidence}`
              }
              accessibilityHint="Highlights it in the list"
              accessibilityState={{ selected: selectedId === transport.id }}
              style={styles.hit}
            >
              <StopMark
                kind="transport"
                icon="transport"
                size="map"
                selected={selectedId === transport.id}
              />
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
                <StopMark
                  kind={isEatKind(p.kind) ? "eat" : "sight"}
                  label={p.ordinal}
                  size="map"
                  selected={isSelected}
                />
              </View>
            </Marker>
          );
        })}
      </Map>

      {status === "failed" ? (
        <MapFailure
          message="The map could not load. This happens without a connection or when the map host is down. The day list still works."
          onRetry={() => {
            setStatus("loading");
            setAttempt((n) => n + 1);
          }}
          listLabel="Show the day list"
          onShowList={onShowList}
        />
      ) : null}
      {status === "loading" ? <MapChip text="Loading the map…" live /> : null}
      {points.length > shownCount ? (
        <MapChip text={`Placing stops ${shownCount} of ${points.length}…`} />
      ) : null}
      {points.length === 0 && !transport ? (
        <MapChip text="Nothing is planned on this day." />
      ) : null}

      <View style={styles.keyCorner}>
        <IconButton
          icon={keyOpen ? "close" : "list"}
          label="Map key"
          hint={keyOpen ? "Hides the key" : "Shows what the marks mean"}
          variant="onMap"
          size="sm"
          onPress={() => setKeyOpen((o) => !o)}
          testID="map-key"
        />
        {keyOpen ? <Legend /> : null}
      </View>

      {/* The sheet of stops curves over the map's lower edge: lift the credit above the curve. */}
      <AttributionBar
        lines={map.attribution}
        userInteractionCount={interactions}
        bottomOffset={radius.xl + spacing.xs}
      />
    </View>
  );
}

export function Legend() {
  return (
    <MapPanel>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <StopMark kind="sight" size="key" />
        </View>
        <Text style={styles.legendText}>Attraction</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <StopMark kind="eat" size="key" />
        </View>
        <Text style={styles.legendText}>Restaurant or café</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <StopMark kind="city" size="key" />
        </View>
        <Text style={styles.legendText}>Your stay</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <StopMark kind="transport" size="key" />
        </View>
        <Text style={styles.legendText}>Travel to a new base city</Text>
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendKey}>
          <View style={styles.swatch} />
        </View>
        <Text style={styles.legendText}>Direct line between stops; dashed if estimated</Text>
      </View>
    </MapPanel>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  clip: { overflow: "hidden" },
  hit: { width: MARKER_SIZE, height: MARKER_SIZE, alignItems: "center", justifyContent: "center" },
  keyCorner: {
    position: "absolute",
    top: spacing.sm,
    right: spacing.sm,
    alignItems: "flex-end",
    gap: spacing.sm,
    maxWidth: 270,
  },
  // Every key sits in the same 20 dp column, so the words line up.
  legendRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 20 },
  legendKey: { width: 20, alignItems: "center", justifyContent: "center" },
  legendText: { ...type.caption, color: colors.text, flexShrink: 1 },
  swatch: { width: 20, height: 0, borderTopWidth: border.thick, borderColor: colors.outline },
});
