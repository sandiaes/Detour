import { fireEvent, render, screen } from "@testing-library/react-native";
import { StyleSheet } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { TOUCH, colors, size } from "../../theme";
import { Button } from "./Button";
import { SearchField, SelectField, Stepper, TextField } from "./fields";
import { Chip, ListRow, SegmentedControl } from "./primitives";
import { ConfirmSheet } from "./Sheet";
import { Notice, StateView } from "./states";

type Host = ReturnType<typeof screen.getByRole>;

function flat(el: Host) {
  return StyleSheet.flatten(el.props.style) ?? {};
}

/** Drawn height plus hit slop: the size a touch lands on. */
function touch(el: Host): number {
  const s = flat(el);
  const own = Math.max(Number(s.minHeight ?? 0), Number(s.height ?? 0));
  const slop = el.props.hitSlop ?? {};
  return own + Number(slop.top ?? 0) + Number(slop.bottom ?? 0);
}

const insets = {
  frame: { x: 0, y: 0, width: 360, height: 640 },
  insets: { top: 24, left: 0, right: 0, bottom: 0 },
};

describe("Button", () => {
  test.each([
    ["primary", colors.primary],
    ["destructive", colors.danger],
    ["secondary", colors.surface],
  ] as const)("the %s variant has its own fill", async (variant, fill) => {
    await render(<Button label="Go" variant={variant} onPress={() => {}} />);
    expect(flat(screen.getByRole("button", { name: "Go" })).backgroundColor).toBe(fill);
  });

  test("both sizes draw 44 or 36 dp and touch at 48 dp", async () => {
    await render(
      <>
        <Button label="Regular" onPress={() => {}} />
        <Button label="Small" size="sm" onPress={() => {}} />
      </>,
    );
    const regular = screen.getByRole("button", { name: "Regular" });
    const small = screen.getByRole("button", { name: "Small" });
    expect(flat(regular).minHeight).toBe(size.control);
    expect(flat(small).minHeight).toBe(size.controlSm);
    expect(touch(regular)).toBeGreaterThanOrEqual(TOUCH);
    expect(touch(small)).toBeGreaterThanOrEqual(TOUCH);
  });

  test("disabled and loading are announced and cannot be pressed", async () => {
    const onPress = jest.fn();
    await render(
      <>
        <Button label="Off" disabled onPress={onPress} />
        <Button label="Busy" loading onPress={onPress} />
      </>,
    );
    const off = screen.getByRole("button", { name: "Off" });
    const busy = screen.getByRole("button", { name: "Busy" });
    expect(off.props.accessibilityState).toMatchObject({ disabled: true });
    expect(busy.props.accessibilityState).toMatchObject({ disabled: true, busy: true });
    await fireEvent.press(off);
    await fireEvent.press(busy);
    expect(onPress).not.toHaveBeenCalled();
  });

  test("a danger tone colours an outlined button's words and border red", async () => {
    await render(
      <Button label="Delete trip" variant="secondary" tone="danger" onPress={() => {}} />,
    );
    const button = screen.getByRole("button", { name: "Delete trip" });
    expect(flat(button).borderColor).toBe(colors.danger);
    expect(screen.getByText("Delete trip")).toHaveStyle({ color: colors.danger });
  });

  test("focus draws a ring", async () => {
    await render(<Button label="Go" onPress={() => {}} />);
    const button = screen.getByRole("button", { name: "Go" });
    await fireEvent(button, "focus");
    expect(flat(screen.getByRole("button", { name: "Go" })).borderColor).toBe(colors.selected);
  });
});

describe("fields", () => {
  test("a text field shows its hint, then its error in words", async () => {
    const view = await render(<TextField label="Title" value="" hint="As on the ticket" />);
    expect(screen.getByText("As on the ticket")).toBeOnTheScreen();
    await view.rerender(<TextField label="Title" value="" error="a title is needed." />);
    expect(screen.getByText("Problem: a title is needed.")).toBeOnTheScreen();
    expect(screen.getByLabelText("Title")).toBeOnTheScreen();
  });

  test("a search field clears with its button", async () => {
    const onClear = jest.fn();
    await render(<SearchField label="Destination" value="Vie" onClear={onClear} />);
    await fireEvent.press(screen.getByRole("button", { name: "Clear the search" }));
    expect(onClear).toHaveBeenCalled();
  });

  test("a select field says its value and whether its list is open", async () => {
    const onToggle = jest.fn();
    await render(
      <SelectField
        label="Day"
        placeholder="Choose a day"
        value="Day 2"
        open={false}
        onToggle={onToggle}
        testID="day"
      />,
    );
    const field = screen.getByRole("button", { name: "Day, Day 2" });
    expect(field.props.accessibilityState).toEqual({ expanded: false });
    expect(touch(field)).toBeGreaterThanOrEqual(TOUCH);
    await fireEvent.press(field);
    expect(onToggle).toHaveBeenCalled();
  });

  test("a stepper stops at its limits and is adjustable", async () => {
    const onChange = jest.fn();
    await render(
      <Stepper
        value={1}
        min={1}
        max={3}
        onChange={onChange}
        format={(n) => `${n} days`}
        accessibilityLabel="Days"
        decreaseLabel="Fewer days"
        increaseLabel="More days"
      />,
    );
    const fewer = screen.getByRole("button", { name: "Fewer days" });
    expect(fewer.props.accessibilityState).toEqual({ disabled: true });
    expect(touch(fewer)).toBeGreaterThanOrEqual(TOUCH);
    await fireEvent.press(screen.getByRole("button", { name: "More days" }));
    expect(onChange).toHaveBeenCalledWith(2);
    expect(screen.getByLabelText("Days").props.accessibilityValue).toMatchObject({
      now: 1,
      text: "1 day".replace("day", "days"),
    });
  });
});

describe("choices", () => {
  test("a segmented control announces the chosen mode", async () => {
    const onChange = jest.fn();
    await render(
      <SegmentedControl
        items={[
          { key: "a", label: "Search" },
          { key: "b", label: "Address" },
        ]}
        value="a"
        onChange={onChange}
        testID="mode"
      />,
    );
    const search = screen.getByRole("tab", { name: "Search" });
    expect(search.props.accessibilityState).toEqual({ selected: true });
    expect(touch(search)).toBeGreaterThanOrEqual(TOUCH);
    await fireEvent.press(screen.getByTestId("mode-b"));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  test("a chip shows a check mark when selected, and says so", async () => {
    await render(<Chip label="Tickets" selected onPress={() => {}} />);
    const chip = screen.getByRole("button", { name: "Tickets" });
    expect(chip.props.accessibilityState).toMatchObject({ selected: true });
    expect(screen.getByTestId("icon-check", { includeHiddenElements: true })).toBeTruthy();
    expect(touch(chip)).toBeGreaterThanOrEqual(TOUCH);
  });

  test("a selected row is tinted and announced", async () => {
    await render(<ListRow title="Day 2" selected onPress={() => {}} density="compact" />);
    const row = screen.getByRole("button", { name: "Day 2" });
    expect(row.props.accessibilityState).toMatchObject({ selected: true });
    expect(flat(row).backgroundColor).toBe(colors.selectedSoft);
    expect(touch(row)).toBeGreaterThanOrEqual(TOUCH);
  });
});

describe("confirmations, states and notices", () => {
  test("a confirmation has a red confirming button and a way back", async () => {
    const onConfirm = jest.fn();
    const onCancel = jest.fn();
    await render(
      <SafeAreaProvider initialMetrics={insets}>
        <ConfirmSheet
          visible
          title="Delete this trip?"
          message="It cannot be undone."
          confirmLabel="Delete the trip"
          onConfirm={onConfirm}
          onCancel={onCancel}
          confirmTestID="yes"
        />
      </SafeAreaProvider>,
    );
    expect(screen.getByRole("header", { name: "Delete this trip?" })).toBeOnTheScreen();
    expect(flat(screen.getByTestId("yes")).backgroundColor).toBe(colors.danger);
    await fireEvent.press(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId("yes"));
    expect(onConfirm).toHaveBeenCalled();
  });

  test("a state view has a title, a sentence and one action", async () => {
    const onPress = jest.fn();
    await render(
      <StateView
        kind="error"
        title="Could not load"
        text="Check the connection."
        action={{ label: "Try again", onPress }}
      />,
    );
    expect(screen.getByText("Could not load")).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Try again" }));
    expect(onPress).toHaveBeenCalled();
  });

  test("a notice says its tone in a word", async () => {
    await render(<Notice tone="warning">Showing trips saved earlier.</Notice>);
    expect(screen.getByText(/Offline\./)).toBeOnTheScreen();
  });
});
