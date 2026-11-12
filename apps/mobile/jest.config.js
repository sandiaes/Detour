module.exports = {
  preset: "jest-expo",
  setupFiles: ["<rootDir>/jest.setup.js"],
  testMatch: ["<rootDir>/src/**/*.test.ts?(x)", "<rootDir>/plugins/**/*.test.js"],
  // @detour/shared is TypeScript source in a workspace package.
  transformIgnorePatterns: [
    "/node_modules/(?!(.pnpm/)?((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@maplibre/.*|openapi-fetch))",
  ],
};
