import { createApiClient } from "@detour/shared";

import { connect, ensureInstallation } from "./connect";
import type { TokenStore } from "./tokenStore";

type Route = (request: Request) => Response | Promise<Response>;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const CONFIG = {
  config_version: "1",
  map: {
    style_url: "https://tiles.example.org/style",
    attribution: [{ text: "OpenFreeMap", url: "https://openfreemap.org" }],
  },
};
const HEALTH = { status: "ok", service: "detour-api", version: "0.1.0", release: null };
const ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

function memoryStore(initial: string | null = null): TokenStore & { value: string | null } {
  const store = {
    value: initial,
    get: async () => store.value,
    set: async (t: string) => {
      store.value = t;
    },
  };
  return store;
}

function fakeBackend(overrides: Record<string, Route> = {}) {
  const calls: { path: string; auth: string | null }[] = [];
  const routes: Record<string, Route> = {
    "GET /v1/health": () => json(HEALTH),
    "GET /v1/config": () => json(CONFIG),
    "POST /v1/installations": () => json({ installation_id: ID, token: "dt1.new" }, 201),
    "GET /v1/installations/me": (r) =>
      r.headers.get("Authorization") === "Bearer dt1.good"
        ? json({ installation_id: ID })
        : json({ detail: "no" }, 401),
    ...overrides,
  };
  const fetchImpl = (async (input: Request) => {
    const path = new URL(input.url).pathname;
    calls.push({ path: `${input.method} ${path}`, auth: input.headers.get("Authorization") });
    const route = routes[`${input.method} ${path}`];
    return route ? route(input) : json({ detail: "not found" }, 404);
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

test("first run: health, config, then registers and stores the token", async () => {
  const store = memoryStore();
  const { fetchImpl, calls } = fakeBackend();
  const result = await connect({ baseUrl: "https://api.example.org/", store, fetch: fetchImpl });

  expect(result.health.version).toBe("0.1.0");
  expect(result.config.map.style_url).toBe("https://tiles.example.org/style");
  expect(result.registered).toBe(true);
  expect(store.value).toBe("dt1.new");
  expect(calls.map((c) => c.path)).toEqual([
    "GET /v1/health",
    "GET /v1/config",
    "POST /v1/installations",
  ]);
});

test("later runs reuse the stored token after the backend accepts it", async () => {
  const store = memoryStore("dt1.good");
  const { fetchImpl, calls } = fakeBackend();
  const result = await connect({ baseUrl: "https://api.example.org", store, fetch: fetchImpl });

  expect(result.registered).toBe(false);
  expect(result.installationId).toBe(ID);
  expect(calls.at(-1)).toEqual({ path: "GET /v1/installations/me", auth: "Bearer dt1.good" });
  expect(calls.some((c) => c.path === "POST /v1/installations")).toBe(false);
});

test("a rejected stored token (secret changed) is replaced by a new registration", async () => {
  const store = memoryStore("dt1.stale");
  const { fetchImpl, calls } = fakeBackend();
  const result = await connect({ baseUrl: "https://api.example.org", store, fetch: fetchImpl });

  expect(result.registered).toBe(true);
  expect(store.value).toBe("dt1.new");
  expect(calls.map((c) => c.path)).toContain("POST /v1/installations");
});

test("a server error during the token check does not throw the token away", async () => {
  const store = memoryStore("dt1.good");
  const { fetchImpl } = fakeBackend({ "GET /v1/installations/me": () => json({}, 500) });
  await expect(
    connect({ baseUrl: "https://api.example.org", store, fetch: fetchImpl }),
  ).rejects.toThrow(/Token check failed \(HTTP 500\)/);
  expect(store.value).toBe("dt1.good");
});

test("fails clearly when the build has no backend URL", async () => {
  await expect(connect({ baseUrl: "", store: memoryStore() })).rejects.toThrow(/no backend URL/);
});

test("rejects a map style that is not HTTPS instead of using it", async () => {
  const { fetchImpl } = fakeBackend({
    "GET /v1/config": () =>
      json({ ...CONFIG, map: { ...CONFIG.map, style_url: "http://x.example" } }),
  });
  await expect(
    connect({ baseUrl: "https://api.example.org", store: memoryStore(), fetch: fetchImpl }),
  ).rejects.toThrow(/not HTTPS/);
});

test("reports an unhealthy backend", async () => {
  const { fetchImpl } = fakeBackend({ "GET /v1/health": () => json({}, 503) });
  await expect(
    connect({ baseUrl: "https://api.example.org", store: memoryStore(), fetch: fetchImpl }),
  ).rejects.toThrow(/Health check failed \(HTTP 503\)/);
});

test("ensureInstallation fails if registration is refused", async () => {
  const { fetchImpl } = fakeBackend({ "POST /v1/installations": () => json({}, 500) });
  const client = createApiClient("https://api.example.org", { fetch: fetchImpl });
  await expect(ensureInstallation(client, memoryStore(), () => {})).rejects.toThrow(
    /Registration failed/,
  );
});
