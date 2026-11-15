import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { AppState } from "react-native";

import { API_URL } from "../config/env";
import { type Connection, ConnectionError, connect } from "./connect";
import { secureTokenStore } from "./tokenStore";

// After this long without an answer the app says the server is waking up (ADR 005: the Render
// free tier needs about a minute after 15 idle minutes).
export const WAKING_AFTER_MS = 4000;

// After a failed connection the app tries again by itself, waiting a little longer each time
// (5 s, 10 s, 20 s, 40 s, then every minute), so a phone that comes back online or a server that
// finishes waking needs no tap on Retry. Retry and returning to the app try at once.
export const RETRY_BASE_MS = 5_000;
export const RETRY_MAX_MS = 60_000;

/** The wait before automatic attempt number `failures` (1 after the first failure). */
export function retryDelayMs(failures: number): number {
  return Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** Math.max(0, failures - 1));
}

export type BackendState =
  | { phase: "connecting"; waking: boolean }
  | { phase: "ready"; connection: Connection }
  | {
      phase: "error";
      message: string;
      /** When the next automatic attempt starts (ms since epoch); null when none is planned. */
      retryAt?: number | null;
    };

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
  // Failed attempts in a row; a ref, as it only shapes the wait and is never drawn.
  const failures = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const wakingTimer = setTimeout(() => {
      if (!cancelled) setState({ phase: "connecting", waking: true });
    }, WAKING_AFTER_MS);

    connect({ baseUrl: API_URL, store: secureTokenStore })
      .then((connection) => {
        if (!cancelled) {
          failures.current = 0;
          setState({ phase: "ready", connection });
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const permanent = e instanceof ConnectionError && e.permanent;
        failures.current += 1;
        setState({
          phase: "error",
          message: describeConnectionError(e),
          retryAt: permanent ? null : Date.now() + retryDelayMs(failures.current),
        });
      })
      .finally(() => clearTimeout(wakingTimer));

    return () => {
      cancelled = true;
      clearTimeout(wakingTimer);
    };
  }, [attempt]);

  // Try again by itself after the planned wait.
  const retryAt = state.phase === "error" ? (state.retryAt ?? null) : null;
  useEffect(() => {
    if (retryAt === null) return;
    const timer = setTimeout(
      () => {
        setState({ phase: "connecting", waking: false });
        setAttempt((n) => n + 1);
      },
      Math.max(0, retryAt - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [retryAt]);

  // Coming back to the app after being offline: try again without asking the user to press Retry.
  useEffect(() => {
    if (state.phase !== "error") return;
    const subscription = AppState.addEventListener("change", (next) => {
      if (next === "active") {
        setState({ phase: "connecting", waking: false });
        setAttempt((n) => n + 1);
      }
    });
    return () => subscription.remove();
  }, [state.phase]);

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

/** What the banner says when the server cannot be reached. Plain words, no stack or address. */
export function describeConnectionError(e: unknown): string {
  if (e instanceof ConnectionError) return e.message;
  // fetch rejects with a TypeError when there is no network and an AbortError on the timeout.
  if (e instanceof Error && e.name === "AbortError") {
    return "The server did not answer in time. The free host may still be starting.";
  }
  return "No connection to the server. Check the phone's internet connection.";
}
