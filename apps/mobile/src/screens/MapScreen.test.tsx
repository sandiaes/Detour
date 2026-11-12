import { render, screen } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { connection, WithBackend } from "../testUtils";
import { MapScreen } from "./MapScreen";

// The native MapLibre view cannot run in Jest. The mock records the style it was given.
const mockMapStyle = jest.fn();
jest.mock("@maplibre/maplibre-react-native", () => ({
  Map: ({ mapStyle, children }: { mapStyle: string; children: ReactNode }) => {
    const { View } = jest.requireActual<typeof import("react-native")>("react-native");
    mockMapStyle(mapStyle);
    return <View testID="map">{children}</View>;
  },
  Camera: () => null,
}));

beforeEach(() => mockMapStyle.mockClear());

test("shows the style URL that the backend sent, and gives it to the map", async () => {
  await render(
    <WithBackend>
      <MapScreen />
    </WithBackend>,
  );
  expect(screen.getByText(/https:\/\/tiles\.example\.org\/styles\/test/)).toBeOnTheScreen();
  expect(mockMapStyle).toHaveBeenCalledWith(connection.config.map.style_url);
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();
});

test("does not invent a style URL while the backend is unavailable", async () => {
  await render(
    <WithBackend state={{ phase: "error", message: "offline" }}>
      <MapScreen />
    </WithBackend>,
  );
  expect(screen.queryByTestId("map")).toBeNull();
  expect(mockMapStyle).not.toHaveBeenCalled();
  expect(screen.getByText("Retry")).toBeOnTheScreen();
});
