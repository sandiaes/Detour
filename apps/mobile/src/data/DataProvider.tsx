import type { ApiClient } from "@detour/shared";
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useBackend } from "../api/BackendProvider";
import { NetworkError } from "../api/unwrap";
import type { CacheStore } from "../cache/store";

// Server state without a library (ADR 015). One in-memory map in front of the on-device cache,
// shared by every screen, with in-flight requests de-duplicated by key. A screen that mounts again
// within `ttlMs` of a successful fetch makes no request.

export const DEFAULT_TTL_MS = 60_000;

type MemoryEntry = { data: unknown; savedAt: number; fetchedInSession: boolean };

export type DataContextValue = {
  cache: CacheStore;
  memory: Map<string, MemoryEntry>;
  inflight: Map<string, Promise<unknown>>;
  /** Screens that show a key are told when `put` or `update` changes it. */
  listeners: Map<string, Set<(entry: MemoryEntry) => void>>;
  /** Forget everything held for keys that start with the prefix (disk and memory). */
  invalidate: (prefix: string) => void;
  /** Drop one key from memory and from the device (a deleted trip must not come back offline). */
  forget: (key: string) => void;
  /** Store a value the app just received (for example from a PATCH), keyed like a read. */
  put: (key: string, data: unknown) => void;
  /** Change a held value in place (memory and device). Does nothing if it is not held. */
  update: <T>(key: string, change: (old: T) => T) => void;
};

const DataContext = createContext<DataContextValue | null>(null);

export function useData(): DataContextValue {
  const value = useContext(DataContext);
  if (!value) throw new Error("useData must be used inside a DataProvider");
  return value;
}

const INSTALLATION_KEY = "meta:installation";

export function DataProvider({ cache, children }: { cache: CacheStore; children: ReactNode }) {
  const { state } = useBackend();
  // One set of maps for the life of the provider.
  const [memory] = useState(() => new Map<string, MemoryEntry>());
  const [inflight] = useState(() => new Map<string, Promise<unknown>>());
  const [listeners] = useState(() => new Map<string, Set<(entry: MemoryEntry) => void>>());
  // Trips on the device belong to the installation that fetched them. A token that no longer
  // belongs to the same installation (a new registration) must not show the old data.
  const installationId = state.phase === "ready" ? state.connection.installationId : null;

  useEffect(() => {
    if (!installationId) return;
    void (async () => {
      const previous = await cache.get<string>(INSTALLATION_KEY);
      if (previous && previous.value !== installationId) {
        memory.clear();
        await cache.clear();
      }
      await cache.set(INSTALLATION_KEY, installationId);
    })();
  }, [installationId, cache, memory]);

  const invalidate = useCallback(
    (prefix: string) => {
      // Only the in-memory copy goes, so the next screen refetches. The saved copy on the device
      // stays (it is what an offline read shows) until the fetch replaces it.
      for (const key of [...memory.keys()]) if (key.startsWith(prefix)) memory.delete(key);
    },
    [memory],
  );

  const forget = useCallback(
    (key: string) => {
      memory.delete(key);
      void cache.remove(key);
    },
    [cache, memory],
  );

  const put = useCallback(
    (key: string, data: unknown) => {
      const entry = { data, savedAt: Date.now(), fetchedInSession: true };
      memory.set(key, entry);
      void cache.set(key, data, entry.savedAt);
      listeners.get(key)?.forEach((notify) => notify(entry));
    },
    [cache, memory, listeners],
  );

  const update = useCallback(
    <T,>(key: string, change: (old: T) => T) => {
      const held = memory.get(key);
      if (held) put(key, change(held.data as T));
    },
    [memory, put],
  );

  const value = useMemo(
    () => ({ cache, memory, inflight, listeners, invalidate, forget, put, update }),
    [cache, memory, inflight, listeners, invalidate, forget, put, update],
  );
  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export type ResourceState<T> = {
  status: "loading" | "ready" | "error";
  data: T | undefined;
  /** When the data shown was fetched (ms). Null while nothing is shown. */
  savedAt: number | null;
  /** True when the data shown is a saved copy, not fetched in this session. */
  fromCache: boolean;
  /** The server could not be reached; the saved copy (if any) is what the screen shows. */
  offline: boolean;
  refreshing: boolean;
  error: unknown;
  /** The backend connection is still being made after a pause: the free host is waking. */
  waking: boolean;
};

export type Resource<T> = ResourceState<T> & {
  refresh: () => void;
  setData: (data: T) => void;
};

const INITIAL: ResourceState<never> = {
  status: "loading",
  data: undefined,
  savedAt: null,
  fromCache: false,
  offline: false,
  refreshing: false,
  error: null,
  waking: false,
};

export function useResource<T>(
  key: string | null,
  load: (client: ApiClient) => Promise<T>,
  options: { ttlMs?: number } = {},
): Resource<T> {
  const ttlMs = options.ttlMs ?? DEFAULT_TTL_MS;
  const { cache, memory, inflight, listeners } = useData();
  const { state: backend, retry } = useBackend();
  const [state, setState] = useState<ResourceState<T>>(INITIAL);
  const [nonce, setNonce] = useState(0);
  const forced = useRef(false);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load; // the latest loader, without making it a dependency of the fetch
  });
  const client = backend.phase === "ready" ? backend.connection.client : null;
  const backendPhase = backend.phase;
  const waking = backend.phase === "connecting" && backend.waking;

  useEffect(() => {
    if (key === null) return;
    let cancelled = false;
    const patch = (p: Partial<ResourceState<T>>) => {
      if (!cancelled) setState((s) => ({ ...s, ...p }));
    };

    void (async () => {
      // 1. Show what is already known: memory first, then the device.
      let known = memory.get(key) as MemoryEntry | undefined;
      let shown = false;
      if (known) {
        patch({
          status: "ready",
          data: known.data as T,
          savedAt: known.savedAt,
          fromCache: !known.fetchedInSession,
        });
        shown = true;
      } else {
        patch({ ...INITIAL, status: "loading" });
        const saved = await cache.get<T>(key);
        if (cancelled) return;
        if (saved) {
          known = { data: saved.value, savedAt: saved.savedAt, fetchedInSession: false };
          memory.set(key, known);
          patch({ status: "ready", data: saved.value, savedAt: saved.savedAt, fromCache: true });
          shown = true;
        }
      }

      // 2. Fetch unless a fresh copy from this session is held.
      const isForced = forced.current;
      forced.current = false;
      const fresh = known?.fetchedInSession && Date.now() - known.savedAt < ttlMs;
      if (!isForced && fresh) {
        patch({ offline: false, error: null, refreshing: false });
        return;
      }
      if (!client) {
        if (backendPhase === "error") {
          // The backend cannot be reached at all: the same as offline for this screen.
          const error = new NetworkError();
          patch(shown ? { offline: true, error } : { status: "error", offline: true, error });
        }
        return; // "connecting": keep waiting; the effect runs again when the client exists
      }

      patch({ refreshing: true, error: null });
      let request = inflight.get(key) as Promise<T> | undefined;
      if (!request) {
        request = loadRef.current(client).finally(() => inflight.delete(key));
        inflight.set(key, request);
      }
      try {
        const data = await request;
        const entry = { data, savedAt: Date.now(), fetchedInSession: true };
        memory.set(key, entry);
        void cache.set(key, data, entry.savedAt);
        patch({
          status: "ready",
          data,
          savedAt: entry.savedAt,
          fromCache: false,
          offline: false,
          refreshing: false,
          error: null,
        });
      } catch (error) {
        const offline = error instanceof NetworkError;
        patch(
          shown
            ? { refreshing: false, offline, error }
            : { status: "error", refreshing: false, offline, error },
        );
      }
    })();

    return () => {
      cancelled = true;
    };
    // `client` identity changes only when the connection is remade.
  }, [key, client, backendPhase, nonce, ttlMs, cache, memory, inflight]);

  // A change made elsewhere in the app (a plan was selected, trips were planned) shows at once.
  useEffect(() => {
    if (key === null) return;
    const notify = (entry: MemoryEntry) =>
      setState((s) => ({
        ...s,
        status: "ready",
        data: entry.data as T,
        savedAt: entry.savedAt,
        fromCache: false,
        error: null,
      }));
    const set = listeners.get(key) ?? new Set();
    set.add(notify);
    listeners.set(key, set);
    return () => {
      set.delete(notify);
    };
  }, [key, listeners]);

  const refresh = useCallback(() => {
    forced.current = true;
    if (backendPhase === "error") retry();
    setNonce((n) => n + 1);
  }, [backendPhase, retry]);

  const setData = useCallback(
    (data: T) => {
      if (key === null) return;
      const entry = { data, savedAt: Date.now(), fetchedInSession: true };
      memory.set(key, entry);
      void cache.set(key, data, entry.savedAt);
      setState((s) => ({ ...s, status: "ready", data, savedAt: entry.savedAt, fromCache: false }));
    },
    [key, cache, memory],
  );

  const shown = key === null ? INITIAL : state;
  return { ...shown, waking, refresh, setData };
}
