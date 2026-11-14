import type { ReactNode } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { type BackendState, BackendContext } from "../api/BackendProvider";
import type { Connection } from "../api/connect";
import { type CacheStore, createMemoryStore } from "../cache/store";
import { DataProvider } from "../data/DataProvider";
import { DocumentsProvider } from "../documents/DocumentsProvider";
import { type DocumentStore, createMemoryDocumentStore } from "../documents/store";
import { type FakeFiles, createFakeFiles } from "./fakeFiles";
import { type Route, NavigationProvider } from "../nav/Navigator";
import { type FakeClient, createFakeClient } from "./fakeClient";

export const MAP_CONFIG = {
  style_url: "https://tiles.example.org/styles/test",
  attribution: [
    { text: "OpenFreeMap", url: "https://openfreemap.org" },
    { text: "Data from OpenStreetMap", url: "https://www.openstreetmap.org/copyright" },
  ],
};

export function makeConnection(client: FakeClient = createFakeClient({})): Connection {
  return {
    health: { status: "ok", service: "detour-api", version: "0.1.0", release: "abcdef1234" },
    config: { config_version: "1", map: MAP_CONFIG },
    installationId: "11111111-2222-3333-4444-555555555555",
    registered: false,
    client,
  } as unknown as Connection;
}

type Props = {
  children: ReactNode;
  /** The client the screens will call. Ignored when `state` is given. */
  client?: FakeClient;
  state?: BackendState;
  cache?: CacheStore;
  initial?: Route;
  retry?: () => void;
  /** The documents on the "device" (ADR 023). */
  documents?: DocumentStore;
  files?: FakeFiles;
};

/** Backend, saved-data cache and navigation around a screen, with a fake server. */
export function Harness({
  children,
  client = createFakeClient({}),
  state,
  cache = createMemoryStore(),
  initial,
  retry = () => {},
  documents = createMemoryDocumentStore(),
  files = createFakeFiles(),
}: Props) {
  const backend: BackendState = state ?? { phase: "ready", connection: makeConnection(client) };
  return (
    <SafeAreaProvider
      initialMetrics={{
        frame: { x: 0, y: 0, width: 360, height: 740 },
        insets: { top: 0, left: 0, right: 0, bottom: 0 },
      }}
    >
      <BackendContext.Provider value={{ state: backend, apiUrl: "https://api.example.org", retry }}>
        <DataProvider cache={cache}>
          <DocumentsProvider store={documents} files={files}>
            <NavigationProvider initial={initial}>{children}</NavigationProvider>
          </DocumentsProvider>
        </DataProvider>
      </BackendContext.Provider>
    </SafeAreaProvider>
  );
}
