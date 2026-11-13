import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import { captureBackButton } from "../testing/backButton";
import { NavigationProvider, useNavigation } from "./Navigator";

function Probe() {
  const nav = useNavigation();
  return (
    <>
      <Text testID="where">{`${nav.route.name}:${nav.depth}`}</Text>
      <Text onPress={() => nav.push({ name: "createTrip" })}>push</Text>
      <Text onPress={() => nav.replace({ name: "trip", tripId: "t" })}>replace</Text>
      <Text onPress={() => nav.switchRoot({ name: "more" })}>more</Text>
    </>
  );
}

const where = () => screen.getByTestId("where").props.children;

test("push, replace and the back button", async () => {
  const back = captureBackButton();
  await render(
    <NavigationProvider>
      <Probe />
    </NavigationProvider>,
  );
  expect(where()).toBe("trips:1");
  await fireEvent.press(screen.getByText("push"));
  expect(where()).toBe("createTrip:2");
  await fireEvent.press(screen.getByText("replace"));
  expect(where()).toBe("trip:2");
  await act(async () => {
    expect(back.press()).toBe(true);
  });
  expect(where()).toBe("trips:1");
  expect(back.press()).toBe(false);
});

test.each(["explore", "photos", "more"] as const)(
  "back from the %s tab returns to Trips before leaving the app",
  async (root) => {
    const back = captureBackButton();
    await render(
      <NavigationProvider initial={{ name: root }}>
        <Probe />
      </NavigationProvider>,
    );
    await act(async () => {
      expect(back.press()).toBe(true);
    });
    expect(where()).toBe("trips:1");
    expect(back.press()).toBe(false);
  },
);

test("switching a root tab drops the screens above it", async () => {
  await render(
    <NavigationProvider>
      <Probe />
    </NavigationProvider>,
  );
  await fireEvent.press(screen.getByText("push"));
  await fireEvent.press(screen.getByText("more"));
  expect(where()).toBe("more:1");
});
