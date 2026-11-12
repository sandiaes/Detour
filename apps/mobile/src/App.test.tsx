import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "./App";
import { WithBackend } from "./testUtils";

jest.mock("@maplibre/maplibre-react-native", () => ({ Map: () => null, Camera: () => null }));

async function open() {
  await render(
    <WithBackend>
      <AppContent />
    </WithBackend>,
  );
}

test("all six placeholder screens can be reached", async () => {
  await open();
  expect(screen.getByRole("header", { name: "Trips" })).toBeOnTheScreen();

  await fireEvent.press(screen.getByText("Create trip"));
  expect(screen.getByRole("header", { name: "Create Trip" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("‹ Trips"));

  await fireEvent.press(screen.getByText("Open itinerary"));
  expect(screen.getByRole("header", { name: "Itinerary" })).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("‹ Trips"));

  await fireEvent.press(screen.getByRole("tab", { name: "Saved Places" }));
  expect(screen.getByRole("header", { name: "Saved Places" })).toBeOnTheScreen();

  await fireEvent.press(screen.getByRole("tab", { name: "Map" }));
  expect(screen.getByText(/Style URL \(from the backend\)/)).toBeOnTheScreen();

  await fireEvent.press(screen.getByRole("tab", { name: "Settings" }));
  expect(screen.getByRole("header", { name: "Settings" })).toBeOnTheScreen();
  expect(screen.getByText("Status: connected")).toBeOnTheScreen();
  expect(screen.getByText(/detour-api 0\.1\.0 \(abcdef1\)/)).toBeOnTheScreen();
});

test("the banner says the server is waking up during a cold start", async () => {
  await render(
    <WithBackend state={{ phase: "connecting", waking: true }}>
      <AppContent />
    </WithBackend>,
  );
  expect(screen.getByText(/Waking the server/)).toBeOnTheScreen();
});

test("a failed connection shows the reason and a retry button", async () => {
  const retry = jest.fn();
  await render(
    <WithBackend
      state={{ phase: "error", message: "Health check failed (HTTP 503)." }}
      retry={retry}
    >
      <AppContent />
    </WithBackend>,
  );
  expect(screen.getByText(/Health check failed \(HTTP 503\)/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Retry"));
  expect(retry).toHaveBeenCalledTimes(1);
});
