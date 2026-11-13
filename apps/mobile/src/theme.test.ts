import { COVER_TONES } from "./components/ds/Cover";
import { TOUCH, colors } from "./theme";

// WCAG 2.x contrast ratio.
function luminance(hex: string): number {
  const channel = (i: number) => {
    const v = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe("text contrast is at least 4.5:1 (WCAG AA)", () => {
  const pairs: [string, string, string][] = [
    ["text", colors.text, colors.background],
    ["text on surface", colors.text, colors.surface],
    ["text on muted surface", colors.text, colors.surfaceMuted],
    ["muted", colors.muted, colors.background],
    ["muted on surface", colors.muted, colors.surface],
    ["muted on muted surface", colors.muted, colors.surfaceMuted],
    ["primary on background", colors.primary, colors.background],
    ["primary on surface", colors.primary, colors.surface],
    ["primary on soft", colors.primary, colors.primarySoft],
    ["on primary", colors.onPrimary, colors.primary],
    ["link", colors.link, colors.background],
    ["warning", colors.warningText, colors.warning],
    ["text on warning", colors.text, colors.warning],
    ["error", colors.errorText, colors.error],
    ["text on error", colors.text, colors.error],
    ["error text on surface", colors.errorText, colors.surface],
    ["error text on muted surface", colors.errorText, colors.surfaceMuted],
    ["marker number", colors.onPrimary, colors.marker],
    ["selected marker number", colors.onPrimary, colors.markerSelected],
    ["on accent", colors.onAccent, colors.accent],
    ["accent on background", colors.accent, colors.background],
    ["accent text on accent soft", colors.accentText, colors.accentSoft],
    ["on ink", colors.onInk, colors.ink],
    ["primary on muted surface", colors.primary, colors.surfaceMuted],
    ["restaurant marker number", colors.onPrimary, colors.eat],
    ...COVER_TONES.flatMap((t, i): [string, string, string][] => [
      [`cover ${i}: text on the near hills`, colors.onImage, t.near],
      [`cover ${i}: text on the middle hills`, colors.onImage, t.mid],
    ]),
  ];
  test.each(pairs)("%s", (_name, fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("the borders that identify a control are at least 3:1 (WCAG 1.4.11)", () => {
  test.each([
    ["outline on background", colors.outline, colors.background],
    ["outline on surface", colors.outline, colors.surface],
    ["primary on surface", colors.primary, colors.surface],
  ])("%s", (_name, fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(3);
  });
});

test("the touch target size is Android's 48 dp", () => {
  expect(TOUCH).toBe(48);
});
