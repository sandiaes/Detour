import type { RestaurantResult } from "@detour/shared";
import { type ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";
import { BackHandler } from "react-native";

// A small stack navigator held in React state (ADR 015). The app has four root tabs (ADR 021:
// Trips, Explore, Photos, More; Add is an action, not a screen) and a handful of pushed screens, so
// a navigation library (and its native screens module) is not needed. The Android back button pops
// the stack, then returns from another root tab to Trips, then leaves the app.

/** The tabs of one trip (ADR 021). */
export type TripSection = "overview" | "itinerary" | "map" | "photos" | "documents";

export type RootName = "trips" | "explore" | "photos" | "more";

export type Route =
  | { name: "trips" }
  | { name: "explore" }
  | { name: "photos" }
  | { name: "more" }
  | { name: "settings" }
  | { name: "tripOverview"; tripId: string; section?: TripSection }
  | { name: "createTrip" }
  | { name: "trip"; tripId: string }
  | { name: "tripSettings"; tripId: string }
  | { name: "pastTrip"; tripId: string }
  | {
      name: "itinerary";
      tripId: string;
      itineraryId: string;
      view: "days" | "map";
      /** 1-based day shown. */
      day: number;
      /** A stop to highlight on arrival (from a place's details). */
      itemId?: string;
    }
  | { name: "placeDetail"; tripId: string; itineraryId: string; itemId: string }
  | { name: "addPlace"; tripId: string; itineraryId: string }
  | {
      name: "addRestaurant";
      tripId: string;
      itineraryId: string;
      /** A place to eat already chosen in the add-place search (ADR 021). */
      preset?: RestaurantResult;
    }
  | { name: "changePreview"; tripId: string; itineraryId: string; changeSetId: string };

export type Navigation = {
  route: Route;
  /** Number of screens on the stack; 1 means a root tab is showing. */
  depth: number;
  push: (route: Route) => void;
  /** Swap the top screen (used after creating a trip, and to switch days list or map). */
  replace: (route: Route) => void;
  back: () => boolean;
  /** Replace the whole stack (the first route is the root). */
  resetTo: (routes: Route[]) => void;
  /** Show a root tab and drop everything above it. */
  switchRoot: (route: Route & { name: RootName }) => void;
};

const NavigationContext = createContext<Navigation | null>(null);

export function useNavigation(): Navigation {
  const value = useContext(NavigationContext);
  if (!value) throw new Error("useNavigation must be used inside a NavigationProvider");
  return value;
}

export function NavigationProvider({
  initial = { name: "trips" },
  children,
}: {
  initial?: Route;
  children: ReactNode;
}) {
  const [stack, setStack] = useState<Route[]>([initial]);

  const back = useCallback((): boolean => {
    if (stack.length > 1) {
      setStack((s) => s.slice(0, -1));
      return true;
    }
    if (stack[0]?.name !== "trips") {
      setStack([{ name: "trips" }]);
      return true;
    }
    return false; // let Android leave the app
  }, [stack]);

  useEffect(() => {
    const subscription = BackHandler.addEventListener("hardwareBackPress", back);
    return () => subscription.remove();
  }, [back]);

  const value: Navigation = {
    route: stack[stack.length - 1] as Route,
    depth: stack.length,
    push: (route) => setStack((s) => [...s, route]),
    replace: (route) => setStack((s) => [...s.slice(0, -1), route]),
    back,
    resetTo: (routes) => setStack(routes.length > 0 ? routes : [{ name: "trips" }]),
    switchRoot: (route) => setStack([route]),
  };
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}
