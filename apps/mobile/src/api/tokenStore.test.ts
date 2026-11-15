import * as SecureStore from "expo-secure-store";

import { secureTokenStore } from "./tokenStore";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
}));

test("a token that cannot be read counts as no token, so the app registers again", async () => {
  (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error("Keystore key gone"));
  await expect(secureTokenStore.get()).resolves.toBeNull();
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce("dt1.x");
  await expect(secureTokenStore.get()).resolves.toBe("dt1.x");
});
