module.exports = {
  preset: "jest-expo",
  testMatch: ["<rootDir>/src/**/*.test.ts?(x)"],
  // @detour/shared is TypeScript source in a workspace package.
  transformIgnorePatterns: [
    "/node_modules/(?!(.pnpm/)?((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@maplibre/.*|openapi-fetch))",
  ],
};
