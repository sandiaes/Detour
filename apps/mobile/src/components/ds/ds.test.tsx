import { fireEvent, render, screen } from "@testing-library/react-native";

import { Cover, coverSeed, coverTone } from "./Cover";
import { ICON_NAMES, Icon } from "./Icon";
import { Badge, ListRow, StatRow, Tabs } from "./primitives";

test("every icon renders and is hidden from screen readers", async () => {
  for (const name of ICON_NAMES) {
    await render(<Icon name={name} />);
    const svg = screen.getByTestId(`icon-${name}`, { includeHiddenElements: true });
    expect(svg.props.accessibilityElementsHidden).toBe(true);
    expect(svg.props.importantForAccessibility).toBe("no-hide-descendants");
  }
});

test("a destination keeps the same cover; different ones vary", () => {
  expect(coverSeed("900101")).toBe(coverSeed("900101"));
  expect(coverTone("900101")).toBe(coverTone("900101"));
  const tones = new Set(["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((k) => coverTone(k)));
  expect(tones.size).toBeGreaterThan(1);
});

test("a cover shows a photo only when one is given, never an invented one", async () => {
  await render(<Cover seedKey="x" height={100} testID="c" />);
  expect(screen.queryByTestId("cover-photo", { includeHiddenElements: true })).toBeNull();
  await render(<Cover seedKey="x" height={100} uri="file:///photo.jpg" testID="c" />);
  expect(screen.getByTestId("cover-photo").props.source).toEqual({ uri: "file:///photo.jpg" });
});

test("tabs announce the selected one and report presses", async () => {
  const onChange = jest.fn();
  await render(
    <Tabs
      items={[
        { key: "a", label: "First" },
        { key: "b", label: "Second", count: 3 },
      ]}
      value="a"
      onChange={onChange}
    />,
  );
  expect(screen.getByRole("tab", { name: "First" }).props.accessibilityState).toEqual({
    selected: true,
  });
  await fireEvent.press(screen.getByRole("tab", { name: "Second (3)" }));
  expect(onChange).toHaveBeenCalledWith("b");
});

test("a disabled row says why in words and cannot be pressed", async () => {
  const onPress = jest.fn();
  await render(<ListRow icon="note" title="Note" detail="Something" disabled onPress={onPress} />);
  const row = screen.getByRole("button", { name: "Note. Something. Coming later" });
  expect(row.props.accessibilityState).toMatchObject({ disabled: true });
  expect(screen.getByText("Coming later")).toBeOnTheScreen();
  await fireEvent.press(row);
  expect(onPress).not.toHaveBeenCalled();
});

test("statistics read as one phrase each; badges carry a word", async () => {
  await render(
    <>
      <StatRow stats={[{ key: "c", icon: "city", value: 5, label: "Cities" }]} />
      <Badge label="Upcoming" tone="primary" />
    </>,
  );
  expect(screen.getByLabelText("5 cities")).toBeOnTheScreen();
  expect(screen.getByText("Upcoming")).toBeOnTheScreen();
});
