jest.mock("@maplibre/maplibre-react-native", () => require("./src/testing/maplibreMock"));
jest.mock("expo-sqlite", () => ({ openDatabaseAsync: jest.fn() }));
