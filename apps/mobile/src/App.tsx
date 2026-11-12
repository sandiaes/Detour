import { StatusBar } from "expo-status-bar";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { BackendProvider } from "./api/BackendProvider";
import { BackendBanner } from "./components/BackendBanner";
import { deviceCacheStore } from "./cache/sqliteStore";
import type { CacheStore } from "./cache/store";
import { DataProvider } from "./data/DataProvider";
import { type Route, NavigationProvider, useNavigation } from "./nav/Navigator";
import { CreateTripScreen } from "./screens/CreateTripScreen";
import { ItineraryScreen } from "./screens/ItineraryScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { TripScreen } from "./screens/TripScreen";
import { TripsScreen } from "./screens/TripsScreen";
import { TOUCH, colors, spacing, type } from "./theme";

const TABS = [
  { key: "trips", label: "Trips" },
  { key: "settings", label: "Settings" },
] as const;

function CurrentScreen({ route }: { route: Route }) {
  switch (route.name) {
    case "trips":
      return <TripsScreen />;
    case "settings":
      return <SettingsScreen />;
    case "createTrip":
      return <CreateTripScreen />;
    case "trip":
      return <TripScreen tripId={route.tripId} />;
    case "itinerary":
      // Keyed so that a different plan never reuses another plan's state.
      return <ItineraryScreen key={route.itineraryId} route={route} />;
  }
}

export function AppContent() {
  const nav = useNavigation();
  const showTabs = nav.depth === 1;
  return (
    <SafeAreaView style={styles.fill}>
      <StatusBar style="dark" />
      <BackendBanner />
      <View style={styles.fill}>
        <CurrentScreen route={nav.route} />
      </View>
      {showTabs ? (
        <View style={styles.tabBar} accessibilityRole="tablist">
          {TABS.map((tab) => {
            const active = nav.route.name === tab.key;
            return (
              <Pressable
                key={tab.key}
                accessibilityRole="tab"
                accessibilityLabel={tab.label}
                accessibilityState={{ selected: active }}
                style={styles.tab}
                onPress={() => nav.switchRoot({ name: tab.key })}
              >
                <Text style={[styles.tabText, active && styles.tabTextActive]}>{tab.label}</Text>
                {/* The active tab has an underline as well as a colour. */}
                <View style={[styles.tabLine, active && styles.tabLineActive]} />
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </SafeAreaView>
  );
}

export default function App({ cache = deviceCacheStore }: { cache?: CacheStore }) {
  return (
    <SafeAreaProvider>
      <BackendProvider>
        <DataProvider cache={cache}>
          <NavigationProvider>
            <AppContent />
          </NavigationProvider>
        </DataProvider>
      </BackendProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.background },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  tab: {
    flex: 1,
    minHeight: TOUCH + 8,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
  },
  tabText: { ...type.small, color: colors.muted, fontWeight: "600" },
  tabTextActive: { color: colors.primary, fontWeight: "700" },
  tabLine: { height: 3, width: 32, borderRadius: 2, backgroundColor: "transparent" },
  tabLineActive: { backgroundColor: colors.primary },
});
