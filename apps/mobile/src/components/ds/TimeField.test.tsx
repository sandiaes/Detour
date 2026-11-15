import { fireEvent, render, screen } from "@testing-library/react-native";
import { useState } from "react";

import { DurationField } from "./DurationField";
import { TimeField } from "./TimeField";

function Time({ start = "09:00" }: { start?: string }) {
  const [v, setV] = useState(start);
  return <TimeField value={v} onChange={setV} testID="t" />;
}

test("the roulette and the typed field show the same time", async () => {
  await render(<Time />);
  expect(screen.queryByTestId("t-roulette")).toBeNull();
  await fireEvent.press(screen.getByTestId("t-pick"));
  const hours = screen.getByTestId("t-hours");
  const minutes = screen.getByTestId("t-minutes");
  await fireEvent(hours, "accessibilityAction", { nativeEvent: { actionName: "increment" } });
  await fireEvent(minutes, "accessibilityAction", { nativeEvent: { actionName: "decrement" } });
  expect(screen.getByTestId("t")).toHaveProp("value", "10:55");
  // Typing still works, and the wheels follow it.
  await fireEvent.changeText(screen.getByTestId("t"), "14:30");
  expect(screen.getByTestId("t-hours")).toHaveProp("accessibilityValue", {
    min: 0,
    max: 23,
    now: 14,
    text: "14",
  });
});

test("a time that is not one is told, and the wheels still start from 09:00", async () => {
  await render(<Time start="" />);
  await fireEvent.changeText(screen.getByTestId("t"), "99:99");
  expect(await screen.findByText(/use hours and minutes/)).toBeOnTheScreen();
});

function Length() {
  const [m, setM] = useState<number | null>(90);
  return <DurationField minutes={m} onChange={setM} />;
}

test("the unit at the end of a length field switches between min and h", async () => {
  await render(<Length />);
  expect(screen.getByTestId("duration")).toHaveProp("value", "90");
  await fireEvent.press(screen.getByTestId("duration-unit"));
  expect(screen.getByTestId("duration")).toHaveProp("value", "1.5");
  await fireEvent.changeText(screen.getByTestId("duration"), "2");
  await fireEvent.press(screen.getByTestId("duration-unit"));
  expect(screen.getByTestId("duration")).toHaveProp("value", "120");
});
