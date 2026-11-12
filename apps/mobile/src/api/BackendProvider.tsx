import { type ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";

import { API_URL } from "../config/env";
import { type Connection, connect } from "./connect";
import { secureTokenStore } from "./tokenStore";

// After this long without an answer the app says the server is waking up (ADR 005: the Render
// free tier needs about a minute after 15 idle minutes).
export const WAKING_AFTER_MS = 4000;

export type BackendState =
  | { phase: "connecting"; waking: boolean }
  | { phase: "ready"; connection: Connection }
  | { phase: "error"; message: string };

export type BackendContextValue = {
  state: BackendState;
  apiUrl: string;
  retry: () => void;
};

export const BackendContext = createContext<BackendContextValue | null>(null);

export function useBackend(): BackendContextValue {
  const value = useContext(BackendContext);
  if (!value) throw new Error("useBackend must be used inside a BackendProvider");
  return value;
}

export function BackendProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BackendState>({ phase: "connecting", waking: false });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const wakingTimer = setTimeout(() => {
      if (!cancelled) setState({ phase: "connecting", waking: true });
    }, WAKING_AFTER_MS);

    connect({ baseUrl: API_URL, store: secureTokenStore })
      .then((connection) => {
        if (!cancelled) setState({ phase: "ready", connection });
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setState({ phase: "error", message: e instanceof Error ? e.message : String(e) });
        }
      })
      .finally(() => clearTimeout(wakingTimer));

    return () => {
      cancelled = true;
      clearTimeout(wakingTimer);
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ phase: "connecting", waking: false });
    setAttempt((n) => n + 1);
  }, []);

  return (
    <BackendContext.Provider value={{ state, apiUrl: API_URL, retry }}>
      {children}
    </BackendContext.Provider>
  );
}
