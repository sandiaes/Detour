import * as SecureStore from "expo-secure-store";

const KEY = "detour.installation.token";

export type TokenStore = {
  get(): Promise<string | null>;
  set(token: string): Promise<void>;
};

/**
 * Keeps the anonymous installation token in the platform's secure storage. A token that cannot be
 * read (the Keystore key is gone, for example after the phone's data was restored from another
 * device) counts as no token: the app registers again instead of failing to connect for ever.
 */
export const secureTokenStore: TokenStore = {
  get: async () => {
    try {
      return await SecureStore.getItemAsync(KEY);
    } catch {
      return null;
    }
  },
  set: (token) => SecureStore.setItemAsync(KEY, token),
};
