import type { ReactNode } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { type BackendState, BackendContext } from "./api/BackendProvider";
import type { Connection } from "./api/connect";

export const connection: Connection = {
  health: { status: "ok", service: "detour-api", version: "0.1.0", release: "abcdef1234" },
  config: {
    config_version: "1",
    map: {
      style_url: "https://tiles.example.org/styles/test",
      attribution: [
        { text: "OpenFreeMap", url: "https://openfreemap.org" },
        { text: "Data from OpenStreetMap", url: "https://www.openstreetmap.org/copyright" },
      ],
    },
  },
  installationId: "11111111-2222-3333-4444-555555555555",
  registered: false,
};

export function WithBackend({
  state = { phase: "ready", connection },
  retry = () => {},
  children,
}: {
  state?: BackendState;
  retry?: () => void;
  children: ReactNode;
}) {
  return (
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 360, height: 640 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <BackendContext.Provider value={{ state, apiUrl: "https://api.example.org", retry }}>
        {children}
      </BackendContext.Provider>
    </SafeAreaProvider>
  );
}
