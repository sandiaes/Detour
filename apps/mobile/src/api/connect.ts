import {
  type ApiClient,
  type ClientConfig,
  type HealthResponse,
  createApiClient,
} from "@detour/shared";

import type { TokenStore } from "./tokenStore";

export type Connection = {
  health: HealthResponse;
  config: ClientConfig;
  installationId: string;
  /** True when this run created a new anonymous installation. */
  registered: boolean;
  /** The typed client, already carrying the installation token. */
  client: ApiClient;
};

export class ConnectionError extends Error {
  /** True when trying again cannot help (a build with no backend URL, a bad configuration). */
  readonly permanent: boolean;
  constructor(message: string, options: { permanent?: boolean } = {}) {
    super(message);
    this.name = "ConnectionError";
    this.permanent = options.permanent ?? false;
  }
}

/** Basic sanity checks on what the backend sent; the app never falls back to built-in values. */
export function assertValidConfig(config: ClientConfig): void {
  if (!config.map.style_url.startsWith("https://")) {
    throw new ConnectionError("The backend sent a map style URL that is not HTTPS.", {
      permanent: true,
    });
  }
  if (config.map.attribution.length === 0) {
    throw new ConnectionError("The backend sent no map attribution.", { permanent: true });
  }
}

/** Reuses the stored token if the backend accepts it; otherwise registers a new installation. */
export async function ensureInstallation(
  client: ApiClient,
  store: TokenStore,
  setToken: (token: string | null) => void,
): Promise<{ installationId: string; registered: boolean }> {
  const stored = await store.get();
  if (stored) {
    setToken(stored);
    const me = await client.GET("/v1/installations/me");
    if (me.data) return { installationId: me.data.installation_id, registered: false };
    if (me.response.status !== 401) {
      throw new ConnectionError(`Token check failed (HTTP ${me.response.status}).`);
    }
  }
  setToken(null);
  const created = await client.POST("/v1/installations");
  if (!created.data) {
    throw new ConnectionError(`Registration failed (HTTP ${created.response.status}).`);
  }
  await store.set(created.data.token);
  setToken(created.data.token);
  return { installationId: created.data.installation_id, registered: true };
}

export type ConnectOptions = {
  baseUrl: string;
  store: TokenStore;
  fetch?: typeof fetch;
  timeoutMs?: number;
};

/** Health first (this absorbs the cold start), then config, then the installation. */
export async function connect(options: ConnectOptions): Promise<Connection> {
  if (!options.baseUrl) {
    throw new ConnectionError(
      "This build has no backend URL. Rebuild the app with the api_url input (docs/android-release.md).",
      { permanent: true },
    );
  }
  let token: string | null = null;
  const client = createApiClient(options.baseUrl, {
    getToken: () => token,
    fetch: options.fetch,
    timeoutMs: options.timeoutMs,
  });

  const health = await client.GET("/v1/health");
  if (!health.data)
    throw new ConnectionError(`Health check failed (HTTP ${health.response.status}).`);

  const config = await client.GET("/v1/config");
  if (!config.data)
    throw new ConnectionError(`Config request failed (HTTP ${config.response.status}).`);
  assertValidConfig(config.data);

  const installation = await ensureInstallation(client, options.store, (t) => {
    token = t;
  });
  return { health: health.data, config: config.data, ...installation, client };
}
