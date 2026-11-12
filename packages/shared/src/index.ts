// Typed client for the Detour backend. The types in ./schema.d.ts are generated from
// openapi.json, which the backend exports (services/api/scripts/export_openapi.py).
// Never edit schema.d.ts by hand: run `npm run generate` at the repository root.
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };

export type ClientConfig = components["schemas"]["ClientConfig"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type InstallationRegistration = components["schemas"]["InstallationRegistration"];
export type InstallationInfo = components["schemas"]["InstallationInfo"];

export type ApiClientOptions = {
  /** Bearer token of the anonymous installation, read on every request. */
  getToken?: () => string | null | undefined;
  /** Abort a request after this long. Render's free tier needs about a minute to wake. */
  timeoutMs?: number;
  /** Replaceable for tests. */
  fetch?: typeof fetch;
};

export const DEFAULT_TIMEOUT_MS = 75_000;

export function createApiClient(baseUrl: string, options: ApiClientOptions = {}) {
  const baseFetch = options.fetch ?? ((input: Request) => fetch(input));
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const withTimeout = async (request: Request): Promise<Response> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await baseFetch(new Request(request, { signal: controller.signal }));
    } finally {
      clearTimeout(timer);
    }
  };

  const auth: Middleware = {
    onRequest({ request }) {
      const token = options.getToken?.();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  };

  const client = createClient<paths>({
    baseUrl: baseUrl.replace(/\/+$/, ""),
    fetch: withTimeout,
  });
  client.use(auth);
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
