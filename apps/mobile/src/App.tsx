import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { Linking, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { BackendProvider } from "./api/BackendProvider";
import { BackendBanner } from "./components/BackendBanner";
import { EdgeFade } from "./components/EdgeFade";
import { deviceCacheStore } from "./cache/sqliteStore";
import type { CacheStore } from "./cache/store";
import { DataProvider } from "./data/DataProvider";
import { deviceDocumentFiles, deviceDocumentStore, deviceExchangeFiles } from "./documents/device";
import { DocumentsProvider } from "./documents/DocumentsProvider";
import { DocumentFormScreen } from "./screens/DocumentFormScreen";
import { DocumentScreen } from "./screens/DocumentScreen";
import { TripDocumentsScreen } from "./screens/TripDocumentsScreen";
import { BottomNav, showsBottomNav } from "./nav/BottomNav";
import { type Route, NavigationProvider, useNavigation } from "./nav/Navigator";
import { AddPlaceScreen } from "./screens/AddPlaceScreen";
import { AddRestaurantScreen } from "./screens/AddRestaurantScreen";
import { ChangePreviewScreen } from "./screens/ChangePreviewScreen";
import { CreateTripScreen } from "./screens/CreateTripScreen";
import { ExportScreen } from "./screens/ExportScreen";
import { ExploreScreen } from "./screens/ExploreScreen";
import { ImportScreen } from "./screens/ImportScreen";
import { ItineraryScreen } from "./screens/ItineraryScreen";
import { MoreScreen } from "./screens/MoreScreen";
import { PastTripScreen } from "./screens/PastTripScreen";
import { PlaceDetailScreen } from "./screens/PlaceDetailScreen";
import { PhotosScreen } from "./screens/PhotosScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { TripOverviewScreen } from "./screens/TripOverviewScreen";
import { EditStopsScreen } from "./screens/EditStopsScreen";
import { OptimizeScreen } from "./screens/OptimizeScreen";
import { ImageCreditsScreen } from "./screens/ImageCreditsScreen";
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
    case "imageCredits":
      return <ImageCreditsScreen />;
    case "exportTrips":
      return <ExportScreen key={route.tripId ?? "all"} tripId={route.tripId} />;
    case "importTrips":
      return <ImportScreen key={route.uri ?? "choose"} uri={route.uri} />;
    case "editStops":
      return <EditStopsScreen tripId={route.tripId} />;
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
    case "tripDocuments":
      return <TripDocumentsScreen tripId={route.tripId} />;
    case "document":
      return (
        <DocumentScreen
          key={route.documentId}
          tripId={route.tripId}
          documentId={route.documentId}
        />
      );
    case "documentForm":
      return (
        <DocumentFormScreen
          key={route.documentId ?? "new"}
          tripId={route.tripId}
          documentId={route.documentId}
          link={route.link}
          category={route.category}
        />
      );
    case "optimize":
      return <OptimizeScreen route={route} />;
    case "addPlace":
      return <AddPlaceScreen route={route} />;
    case "addRestaurant":
      return <AddRestaurantScreen route={route} />;
    case "changePreview":
      return <ChangePreviewScreen key={route.changeSetId} route={route} />;
  }
}

/** The cover of a trip's Overview, Itinerary and other tabs runs under the status bar, so a fade
 * there would wash over the photo; everywhere else the screen starts below it. */
function coverUnderStatusBar(route: Route): boolean {
  return route.name === "tripOverview" && route.section !== "map";
}

/** A trip file opened with the app (ADR 028): a content or file link goes to the import screen. */
export function isTripFileLink(url: string | null | undefined): url is string {
  return typeof url === "string" && /^(content|file):\/\//.test(url);
}

function useOpenedTripFile() {
  const nav = useNavigation();
  useEffect(() => {
    const open = (url: string | null | undefined) => {
      if (isTripFileLink(url)) nav.push({ name: "importTrips", uri: url });
    };
    void Linking.getInitialURL().then(open, () => undefined);
    const sub = Linking.addEventListener("url", (e) => open(e.url));
    return () => sub.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

export function AppContent() {
  const nav = useNavigation();
  useOpenedTripFile();
  const bottomNav = showsBottomNav(nav.route, nav.depth);
  return (
    <SafeAreaView style={styles.fill}>
      <StatusBar style="dark" />
      <BackendBanner />
      <View style={styles.fill}>
        <CurrentScreen route={nav.route} />
        {/* Soft edges instead of hard lines at the top and above the bottom bar. The plan screen
            keeps its own choose bar at the bottom, so it gets no fade there. */}
        {coverUnderStatusBar(nav.route) ? null : <EdgeFade edge="top" size={10} />}
        {bottomNav && nav.route.name !== "itinerary" ? <EdgeFade edge="bottom" size={14} /> : null}
      </View>
      {bottomNav ? <BottomNav /> : null}
    </SafeAreaView>
  );
}

export default function App({ cache = deviceCacheStore }: { cache?: CacheStore }) {
  return (
    <SafeAreaProvider>
      <BackendProvider>
        <DataProvider cache={cache}>
          <DocumentsProvider
            store={deviceDocumentStore}
            files={deviceDocumentFiles}
            exchange={deviceExchangeFiles}
          >
            <NavigationProvider>
              <AppContent />
            </NavigationProvider>
          </DocumentsProvider>
        </DataProvider>
      </BackendProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.background },
});
