import { Camera, Map } from "@maplibre/maplibre-react-native";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { AttributionBar } from "../components/AttributionBar";
import { Button } from "../components/Button";
import { colors } from "../theme";

// A view position (central Europe), not a provider setting. Real centring comes with trips.
const START = { center: [14.4378, 50.0755] as [number, number], zoom: 4 };

export function MapScreen() {
  const { state, retry } = useBackend();
  const [interactions, setInteractions] = useState(0);
  const [mapStatus, setMapStatus] = useState<"loading" | "loaded" | "failed">("loading");

  if (state.phase !== "ready") {
    return (
      <View style={styles.centre}>
        <Text style={styles.title}>Map</Text>
        <Text style={styles.body}>
          {state.phase === "error"
            ? "The map style comes from the backend, which could not be reached."
            : "Waiting for the map configuration from the backend…"}
        </Text>
        {state.phase === "error" ? <Button label="Retry" onPress={retry} /> : null}
      </View>
    );
  }

  const { map } = state.connection.config;
  return (
    <View style={styles.fill}>
      <Map
        style={styles.fill}
        mapStyle={map.style_url}
        logo={false}
        attribution={false}
        onDidFinishLoadingMap={() => setMapStatus("loaded")}
        onDidFailLoadingMap={() => setMapStatus("failed")}
        // Only a user gesture counts: the map's own initial camera move also fires this event.
        onRegionWillChange={(e) => {
          if (e.nativeEvent.userInteraction) setInteractions((n) => n + 1);
        }}
      >
        <Camera initialViewState={START} />
      </Map>

      <View style={styles.info} accessibilityLiveRegion="polite">
        <Text style={styles.infoText}>
          Map: {mapStatus === "failed" ? "failed to load" : mapStatus}
        </Text>
        <Text style={styles.infoText} numberOfLines={1}>
          Style URL (from the backend): {map.style_url}
        </Text>
      </View>

      <AttributionBar lines={map.attribution} userInteractionCount={interactions} />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  centre: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 12 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  body: { fontSize: 15, textAlign: "center", color: colors.text },
  info: {
    position: "absolute",
    top: 8,
    left: 8,
    right: 8,
    padding: 8,
    backgroundColor: "rgba(255,255,255,0.9)",
    borderRadius: 6,
  },
  infoText: { fontSize: 12, color: colors.text },
});
