// Spike S1 (throwaway): how the app obtains the map style URL.
//
// The style URL and the attribution lines are NOT constants in the app. They are fields of the
// backend's client configuration (GET /v1/config, architecture.md section 4.2 "config"). The
// only build-time value is the backend's base URL.
//
// The spike has no backend yet, so an APK built without EXPO_PUBLIC_DETOUR_API_URL reads a
// bundled stand-in file with the same shape and says so on screen. Phase 1 removes the stand-in.
import standIn from "../spike-config.json";

export type AttributionItem = { text: string; url: string };

export type ClientConfig = {
  config_version: string;
  map: { style_url: string; attribution: AttributionItem[] };
};

export type LoadedConfig = {
  config: ClientConfig;
  source: "backend" | "bundled stand-in";
  from: string;
};

// Inlined by Expo at build time from the environment of the build job.
const API_URL = process.env.EXPO_PUBLIC_DETOUR_API_URL ?? "";

// Render's free web service takes about a minute to wake (ADR 005).
const TIMEOUT_MS = 75_000;

function fail(msg: string): never {
  throw new Error(`Invalid config: ${msg}`);
}

export function parseConfig(raw: unknown): ClientConfig {
  if (typeof raw !== "object" || raw === null) fail("not an object");
  const r = raw as Record<string, unknown>;
  const map = r.map as Record<string, unknown> | undefined;
  if (typeof r.config_version !== "string") fail("config_version");
  if (!map || typeof map !== "object") fail("map");
  const style = map.style_url;
  if (typeof style !== "string" || !style.startsWith("https://")) fail("map.style_url");
  const attribution = map.attribution;
  if (!Array.isArray(attribution) || attribution.length === 0) fail("map.attribution");
  const items = attribution.map((a: unknown) => {
    const x = a as Record<string, unknown>;
    if (typeof x?.text !== "string" || typeof x?.url !== "string") fail("attribution item");
    return { text: x.text as string, url: x.url as string };
  });
  return { config_version: r.config_version as string, map: { style_url: style, attribution: items } };
}

export async function loadConfig(): Promise<LoadedConfig> {
  if (!API_URL) {
    return { config: parseConfig(standIn), source: "bundled stand-in", from: "spike-config.json" };
  }
  const url = `${API_URL.replace(/\/+$/, "")}/v1/config`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" }, signal: ctrl.signal });
    if (!res.ok) throw new Error(`GET ${url} returned HTTP ${res.status}`);
    return { config: parseConfig(await res.json()), source: "backend", from: url };
  } finally {
    clearTimeout(timer);
  }
}
