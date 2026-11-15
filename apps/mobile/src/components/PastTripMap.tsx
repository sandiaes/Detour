import type { ClientConfig } from "@detour/shared";
import { Camera, Map, Marker, type CameraRef } from "@maplibre/maplibre-react-native";
import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useProgressiveCount } from "../data/useProgressive";
import { type PastPoint, VISIT_KIND_LABEL, dayColor } from "../domain/pastTrip";
import { boundsOf } from "../domain/itinerary";
import { colors, radius, shadow, spacing, type } from "../theme";
import { AttributionBar } from "./AttributionBar";
import { Button } from "./Button";
import { Icon } from "./ds/Icon";
import { Notice } from "./ui";

const PADDING = { top: 72, right: 56, bottom: 72, left: 56 };
const CITY_SIZE = 26;
const ATTRACTION_SIZE = 22;
const SELECTED_SIZE = 32;
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
                  <View
                    style={[
                      isCity ? styles.city : styles.attraction,
                      !isCity && { backgroundColor: dayColor(p.day) },
                      selectedId === p.id && styles.selected,
                    ]}
                  >
                    {isCity ? <Icon name="city" size={14} color={colors.onPrimary} /> : null}
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
          <View style={styles.selectedRow}>
            <View
              style={[
                styles.selectedDot,
                { backgroundColor: selected.kind === "city" ? colors.ink : dayColor(selected.day) },
              ]}
            >
              <Icon
                name={selected.kind === "city" ? "city" : "sight"}
                size={16}
                color={colors.onPrimary}
              />
            </View>
            <View style={styles.selectedText}>
              <Text style={styles.title} numberOfLines={2}>
                {selected.name}
              </Text>
              <Text style={styles.meta}>
                {VISIT_KIND_LABEL[selected.kind]} · Day {selected.day}
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close details"
              hitSlop={12}
              onPress={() => setSelectedId(null)}
              style={styles.close}
            >
              <Icon name="close" size={18} color={colors.muted} />
            </Pressable>
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
                <View style={[styles.dayDot, { backgroundColor: dayColor(d) }]} />
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
    width: TOUCH_SIZE,
    height: TOUCH_SIZE,
    minHeight: TOUCH_SIZE,
    alignItems: "center",
    justifyContent: "center",
  },
  // The same small flat markers as a plan's map: cities navy and square-ish, attractions teal and
  // round, a thin white edge, a light shadow; the chosen one larger.
  city: {
    width: CITY_SIZE,
    height: CITY_SIZE,
    borderRadius: 8,
    backgroundColor: colors.ink,
    borderWidth: 2,
    borderColor: colors.onPrimary,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  attraction: {
    width: ATTRACTION_SIZE,
    height: ATTRACTION_SIZE,
    borderRadius: ATTRACTION_SIZE / 2,
    backgroundColor: colors.marker,
    borderWidth: 2,
    borderColor: colors.onPrimary,
    ...shadow.card,
  },
  selected: {
    width: SELECTED_SIZE,
    height: SELECTED_SIZE,
    borderRadius: SELECTED_SIZE / 2,
    backgroundColor: colors.markerSelected,
  },
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
    backgroundColor: colors.background,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    minHeight: 64,
    justifyContent: "center",
  },
  title: { ...type.body, fontWeight: "700", color: colors.text },
  meta: { ...type.caption, color: colors.muted },
  selectedRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  selectedDot: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  selectedText: { flex: 1, gap: 1 },
  close: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  days: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  dayChip: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  dayDot: { width: 12, height: 12, borderRadius: 6 },
  legendText: { ...type.caption, color: colors.muted, flexShrink: 1 },
});
