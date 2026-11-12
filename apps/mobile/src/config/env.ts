// The only build-time value: the backend's base URL, inlined by Expo from the environment of the
// build job (workflow input api_url, or the DETOUR_API_URL repository variable). Everything else,
// including the map style URL, is served by the backend (GET /v1/config).
export const API_URL: string = process.env.EXPO_PUBLIC_DETOUR_API_URL ?? "";
