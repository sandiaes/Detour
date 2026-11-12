import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { BackendProvider } from "./api/BackendProvider";
import { BackendBanner } from "./components/BackendBanner";
import { CreateTripScreen } from "./screens/CreateTripScreen";
import { ItineraryScreen } from "./screens/ItineraryScreen";
import { MapScreen } from "./screens/MapScreen";
import { SavedPlacesScreen } from "./screens/SavedPlacesScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { TripsScreen } from "./screens/TripsScreen";
import { colors } from "./theme";

// No navigation library yet: the choice is recorded in an ADR in Phase 5 (architecture.md 4.1).
// Four tabs, plus Create Trip and Itinerary opened from the Trips tab.
type Tab = "trips" | "map" | "saved" | "settings";
type Route = Tab | "createTrip" | "itinerary";

const TABS: { key: Tab; label: string }[] = [
  { key: "trips", label: "Trips" },
  { key: "map", label: "Map" },
  { key: "saved", label: "Saved Places" },
  { key: "settings", label: "Settings" },
];

export function AppContent() {
  const [route, setRoute] = useState<Route>("trips");
  const activeTab: Tab = route === "createTrip" || route === "itinerary" ? "trips" : route;

  return (
    <SafeAreaView style={styles.fill}>
      <StatusBar style="dark" />
      <BackendBanner />
      {route === "createTrip" || route === "itinerary" ? (
        <Pressable accessibilityRole="button" style={styles.back} onPress={() => setRoute("trips")}>
          <Text style={styles.backText}>‹ Trips</Text>
        </Pressable>
      ) : null}
      <View style={styles.fill}>
        {route === "trips" ? (
          <TripsScreen
            onCreateTrip={() => setRoute("createTrip")}
            onOpenItinerary={() => setRoute("itinerary")}
          />
        ) : null}
        {route === "createTrip" ? <CreateTripScreen /> : null}
        {route === "itinerary" ? <ItineraryScreen /> : null}
        {route === "map" ? <MapScreen /> : null}
        {route === "saved" ? <SavedPlacesScreen /> : null}
        {route === "settings" ? <SettingsScreen /> : null}
      </View>
      <View style={styles.tabBar} accessibilityRole="tablist">
        {TABS.map((tab) => (
          <Pressable
            key={tab.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: activeTab === tab.key }}
            style={styles.tab}
            onPress={() => setRoute(tab.key)}
          >
            <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
              {tab.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <BackendProvider>
        <AppContent />
      </BackendProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.background },
  back: { paddingHorizontal: 16, paddingTop: 12 },
  backText: { fontSize: 16, color: colors.link },
  tabBar: { flexDirection: "row", borderTopWidth: 1, borderTopColor: colors.border },
  tab: { flex: 1, alignItems: "center", paddingVertical: 14 },
  tabText: { fontSize: 13, color: colors.muted },
  tabTextActive: { color: colors.primary, fontWeight: "700" },
});
