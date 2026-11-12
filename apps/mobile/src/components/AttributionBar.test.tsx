import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { Linking } from "react-native";

import { AttributionBar, COLLAPSE_AFTER_MS } from "./AttributionBar";

const lines = [
  { text: "OpenFreeMap", url: "https://openfreemap.org" },
  { text: "Data from OpenStreetMap", url: "https://www.openstreetmap.org/copyright" },
];

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test("credits are visible at start, without any interaction", async () => {
  await render(<AttributionBar lines={lines} />);
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();
  expect(screen.getByText("Data from OpenStreetMap")).toBeOnTheScreen();
  expect(screen.queryByLabelText("Show map attribution")).toBeNull();
});

test("credits stay for five seconds, then collapse to an i button that brings them back", async () => {
  await render(<AttributionBar lines={lines} />);

  await act(async () => {
    jest.advanceTimersByTime(COLLAPSE_AFTER_MS - 1);
  });
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();

  await act(async () => {
    jest.advanceTimersByTime(1);
  });
  expect(screen.queryByText("OpenFreeMap")).toBeNull();

  await fireEvent.press(screen.getByLabelText("Show map attribution"));
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();
});

test("a user gesture on the map collapses the credits at once", async () => {
  const view = await render(<AttributionBar lines={lines} userInteractionCount={0} />);
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();

  await view.rerender(<AttributionBar lines={lines} userInteractionCount={1} />);
  expect(screen.queryByText("OpenFreeMap")).toBeNull();
  expect(screen.getByLabelText("Show map attribution")).toBeOnTheScreen();
});

test("an unchanged interaction count (the map's own camera move) does not collapse them", async () => {
  const view = await render(<AttributionBar lines={lines} userInteractionCount={0} />);
  await view.rerender(<AttributionBar lines={lines} userInteractionCount={0} />);
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();
});

test("each credit opens its page", async () => {
  const open = jest.spyOn(Linking, "openURL").mockResolvedValue();
  await render(<AttributionBar lines={lines} />);
  await fireEvent.press(screen.getByText("Data from OpenStreetMap"));
  expect(open).toHaveBeenCalledWith("https://www.openstreetmap.org/copyright");
});
