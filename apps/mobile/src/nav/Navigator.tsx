import { type ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";
import { BackHandler } from "react-native";

// A small stack navigator held in React state (ADR 015). The app has two root tabs and four
// pushed screens, so a navigation library (and its native screens module) is not needed. The
// Android back button pops the stack, then returns from Settings to Trips, then leaves the app.

export type Route =
  | { name: "trips" }
  | { name: "settings" }
  | { name: "createTrip" }
  | { name: "trip"; tripId: string }
  | {
      name: "itinerary";
      tripId: string;
      itineraryId: string;
      view: "days" | "map";
      /** 1-based day shown on the map. */
      day: number;
    };

export type Navigation = {
  route: Route;
  /** Number of screens on the stack; 1 means a root tab is showing. */
  depth: number;
  push: (route: Route) => void;
  /** Swap the top screen (used after creating a trip, and to switch days list or map). */
  replace: (route: Route) => void;
  back: () => boolean;
  /** Show a root tab and drop everything above it. */
  switchRoot: (route: Route & { name: "trips" | "settings" }) => void;
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
    if (stack[0]?.name === "settings") {
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
    switchRoot: (route) => setStack([route]),
  };
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}
