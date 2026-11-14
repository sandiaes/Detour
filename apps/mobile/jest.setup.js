jest.mock("@maplibre/maplibre-react-native", () => require("./src/testing/maplibreMock"));
jest.mock("expo-sqlite", () => ({ openDatabaseAsync: jest.fn() }));
// The native file module is never reached in tests: screens get testing/fakeFiles.ts.
jest.mock("expo-file-system", () => ({ Directory: class {}, File: class {}, Paths: {} }));
