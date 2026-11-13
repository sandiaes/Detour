import { StatusBar } from "expo-status-bar";
import { StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { BackendProvider } from "./api/BackendProvider";
import { BackendBanner } from "./components/BackendBanner";
import { deviceCacheStore } from "./cache/sqliteStore";
import type { CacheStore } from "./cache/store";
import { DataProvider } from "./data/DataProvider";
import { BottomNav, showsBottomNav } from "./nav/BottomNav";
import { type Route, NavigationProvider, useNavigation } from "./nav/Navigator";
import { AddPlaceScreen } from "./screens/AddPlaceScreen";
import { AddRestaurantScreen } from "./screens/AddRestaurantScreen";
import { ChangePreviewScreen } from "./screens/ChangePreviewScreen";
import { CreateTripScreen } from "./screens/CreateTripScreen";
import { ExploreScreen } from "./screens/ExploreScreen";
import { ItineraryScreen } from "./screens/ItineraryScreen";
import { MoreScreen } from "./screens/MoreScreen";
import { PastTripScreen } from "./screens/PastTripScreen";
import { PlaceDetailScreen } from "./screens/PlaceDetailScreen";
import { PhotosScreen } from "./screens/PhotosScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { TripOverviewScreen } from "./screens/TripOverviewScreen";
import { TripScreen } from "./screens/TripScreen";
import { TripSettingsScreen } from "./screens/TripSettingsScreen";
import { TripsScreen } from "./screens/TripsScreen";
import { colors } from "./theme";

function CurrentScreen({ route }: { route: Route }) {
  switch (route.name) {
    case "trips":
      return <TripsScreen />;
    case "explore":
      return <ExploreScreen />;
    case "photos":
      return <PhotosScreen />;
    case "more":
      return <MoreScreen />;
    case "settings":
      return <SettingsScreen />;
    case "tripOverview":
      // Keyed so that another trip never reuses this one's tab state.
      return (
        <TripOverviewScreen key={route.tripId} tripId={route.tripId} section={route.section} />
      );
    case "createTrip":
      return <CreateTripScreen />;
    case "trip":
      return <TripScreen tripId={route.tripId} />;
    case "tripSettings":
      return <TripSettingsScreen tripId={route.tripId} />;
    case "pastTrip":
      return <PastTripScreen key={route.tripId} tripId={route.tripId} />;
    case "itinerary":
      // Keyed so that a different plan never reuses another plan's state.
      return <ItineraryScreen key={route.itineraryId} route={route} />;
    case "placeDetail":
      return (
        <PlaceDetailScreen
          key={route.itemId}
          tripId={route.tripId}
          itineraryId={route.itineraryId}
          itemId={route.itemId}
        />
      );
    case "addPlace":
      return <AddPlaceScreen route={route} />;
    case "addRestaurant":
      return <AddRestaurantScreen route={route} />;
    case "changePreview":
      return <ChangePreviewScreen key={route.changeSetId} route={route} />;
  }
}

export function AppContent() {
  const nav = useNavigation();
  return (
    <SafeAreaView style={styles.fill}>
      <StatusBar style="dark" />
      <BackendBanner />
      <View style={styles.fill}>
        <CurrentScreen route={nav.route} />
      </View>
      {showsBottomNav(nav.route, nav.depth) ? <BottomNav /> : null}
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
});
