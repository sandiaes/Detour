import * as SecureStore from "expo-secure-store";

const KEY = "detour.installation.token";

export type TokenStore = {
  get(): Promise<string | null>;
  set(token: string): Promise<void>;
};

/** Keeps the anonymous installation token in the platform's secure storage. */
export const secureTokenStore: TokenStore = {
  get: () => SecureStore.getItemAsync(KEY),
  set: (token) => SecureStore.setItemAsync(KEY, token),
};
