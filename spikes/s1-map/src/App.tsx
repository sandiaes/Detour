// Spike S1 (throwaway): one screen with an OpenFreeMap map rendered by MapLibre React Native.
import { Camera, Map } from "@maplibre/maplibre-react-native";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useRef, useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { type LoadedConfig, loadConfig } from "./config";

// Florence, the same centre as the spike fixtures. A view position, not a provider setting.
const START = { center: [11.2558, 43.7696] as [number, number], zoom: 13 };

// OSMF attribution guidelines: visible without interaction; may collapse after five seconds
// or on map interaction, if it can still be found again (the (i) button below).
const COLLAPSE_MS = 5000;

type MapState = "loading" | "loaded" | "failed";

export default function App() {
  const [loaded, setLoaded] = useState<LoadedConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mapState, setMapState] = useState<MapState>("loading");
  const [expanded, setExpanded] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchConfig = useCallback(() => {
    setError(null);
    setLoaded(null);
    loadConfig()
      .then(setLoaded)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(fetchConfig, [fetchConfig]);

  const expand = useCallback(() => {
    setExpanded(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setExpanded(false), COLLAPSE_MS);
  }, []);

  useEffect(() => {
    if (loaded) expand();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [loaded, expand]);

  if (error) {
    return (
      <View style={styles.centre}>
        <Text style={styles.title}>Could not load the map configuration</Text>
        <Text style={styles.body}>{error}</Text>
        <Pressable accessibilityRole="button" style={styles.button} onPress={fetchConfig}>
          <Text style={styles.buttonText}>Retry</Text>
        </Pressable>
      </View>
    );
  }
  if (!loaded) {
    return (
      <View style={styles.centre}>
        <Text style={styles.body}>Loading map configuration…</Text>
      </View>
    );
  }

  const { config, source, from } = loaded;
  return (
    <View style={styles.fill}>
      <StatusBar style="dark" />
      <Map
        style={styles.fill}
        mapStyle={config.map.style_url}
        attribution
        attributionPosition={{ bottom: 8, right: 8 }}
        logo={false}
        onDidFinishLoadingMap={() => setMapState("loaded")}
        onDidFailLoadingMap={() => setMapState("failed")}
        onRegionWillChange={() => setExpanded(false)}
      >
        <Camera initialViewState={START} />
      </Map>

      <View style={styles.info} accessibilityLiveRegion="polite">
        <Text style={styles.infoText}>Detour spike S1</Text>
        <Text style={styles.infoText}>
          Map: {mapState === "loaded" ? "loaded" : mapState === "failed" ? "FAILED to load" : "loading…"}
        </Text>
        <Text style={styles.infoText}>Config: {source} ({config.config_version})</Text>
        <Text style={styles.infoText} numberOfLines={1}>From: {from}</Text>
        <Text style={styles.infoText} numberOfLines={1}>Style: {config.map.style_url}</Text>
      </View>

      {expanded ? (
        <View style={styles.attribution} accessibilityLabel="Map attribution">
          {config.map.attribution.map((a) => (
            <Text
              key={a.url}
              style={styles.link}
              accessibilityRole="link"
              onPress={() => Linking.openURL(a.url)}
            >
              {a.text}
            </Text>
          ))}
        </View>
      ) : (
        <Pressable
          style={styles.infoButton}
          accessibilityRole="button"
          accessibilityLabel="Show map attribution"
          onPress={expand}
          hitSlop={12}
        >
          <Text style={styles.infoButtonText}>i</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  centre: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  title: { fontSize: 18, fontWeight: "600", marginBottom: 8, textAlign: "center" },
  body: { fontSize: 15, textAlign: "center" },
  button: { marginTop: 16, paddingHorizontal: 20, paddingVertical: 12, backgroundColor: "#1f4e79", borderRadius: 6 },
  buttonText: { color: "#fff", fontSize: 16 },
  info: { position: "absolute", top: 40, left: 8, right: 8, padding: 8, backgroundColor: "rgba(255,255,255,0.9)", borderRadius: 6 },
  infoText: { fontSize: 12, color: "#111" },
  attribution: { position: "absolute", left: 8, bottom: 8, flexDirection: "row", flexWrap: "wrap", maxWidth: "75%", paddingHorizontal: 6, paddingVertical: 4, backgroundColor: "rgba(255,255,255,0.9)", borderRadius: 4 },
  link: { fontSize: 12, color: "#0b4f8a", textDecorationLine: "underline", marginRight: 6 },
  infoButton: { position: "absolute", left: 8, bottom: 8, width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.9)", borderWidth: 1, borderColor: "#666" },
  infoButtonText: { fontSize: 16, fontWeight: "700", color: "#111" },
});
