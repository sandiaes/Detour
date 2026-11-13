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

// Trips, itineraries and search (Phases 2 and 4).
export type Trip = components["schemas"]["Trip"];
export type TripCreate = components["schemas"]["TripCreate"];
export type Itinerary = components["schemas"]["Itinerary"];
export type ItinerarySummary = components["schemas"]["ItinerarySummary"];
export type Day = components["schemas"]["Day"];
export type Item = components["schemas"]["Item"];
export type Transfer = components["schemas"]["Transfer"];
export type PlanNote = components["schemas"]["PlanNote"];
export type PlanStats = components["schemas"]["PlanStats"];
export type GenerationResult = components["schemas"]["GenerationResult"];
export type DestinationResult = components["schemas"]["DestinationResult"];
export type DestinationSearchResponse = components["schemas"]["DestinationSearchResponse"];
export type AttributionEntry = components["schemas"]["AttributionEntry"];
export type PlaceSummary = components["schemas"]["PlaceSummary"];
export type PlaceDetail = components["schemas"]["PlaceDetail"];
export type PlaceSearchResponse = components["schemas"]["PlaceSearchResponse"];
export type ExternalPlace = components["schemas"]["ExternalPlace"];
export type UserPlace = components["schemas"]["UserPlace"];
export type UserPlaceCreate = components["schemas"]["UserPlaceCreate"];
export type UserPlaceUpdate = components["schemas"]["UserPlaceUpdate"];

// Adding and removing places (Phase 7, ADR 018).
export type ChangeSet = components["schemas"]["ChangeSet"];
export type ChangeSetCreate = components["schemas"]["ChangeSetCreate"];
export type RestaurantResult = components["schemas"]["RestaurantResult"];
export type ExternalRestaurant = components["schemas"]["ExternalRestaurant"];
export type RestaurantSearchResponse = components["schemas"]["RestaurantSearchResponse"];
export type SlotRequest = components["schemas"]["SlotRequest"];
export type SlotSuggestion = components["schemas"]["SlotSuggestion"];
export type SlotSuggestions = components["schemas"]["SlotSuggestions"];
export type ChangeSetApplied = components["schemas"]["ChangeSetApplied"];
export type ChangeDiff = components["schemas"]["ChangeDiff"];

// The past-trips archive (ADR 006).
export type TripVisit = components["schemas"]["TripVisit"];
export type ArchiveInfo = components["schemas"]["ArchiveInfo"];

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
