// Design tokens. Calm and minimal: warm paper background, deep green as the single accent, plain
// system type, generous spacing, no heavy shadows. Every text/background pair is checked against
// WCAG AA in theme.test.ts (4.5:1 for text, 3:1 for the borders that identify a control).
export const colors = {
  background: "#faf8f4",
  surface: "#ffffff",
  surfaceMuted: "#f1ece2",
  text: "#1e2a2d",
  muted: "#566067",
  primary: "#1d5b55",
  onPrimary: "#ffffff",
  primarySoft: "#e1eeeb",
  /** Hairline dividers only. Never the sole identification of a control. */
  border: "#ddd7ca",
  /** Borders that identify a control (inputs, chips): at least 3:1 on the background. */
  outline: "#778286",
  warning: "#fff3d6",
  warningText: "#5c3d00",
  error: "#fbe6e3",
  errorText: "#8a1c13",
  link: "#0b4f8a",
  /** Map marker disc and its number: white on this, 7:1. */
  marker: "#1d5b55",
  markerSelected: "#1e2a2d",
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 8, md: 14, pill: 999 };

export const type = {
  display: { fontSize: 28, lineHeight: 34, fontWeight: "700" as const },
  title: { fontSize: 22, lineHeight: 28, fontWeight: "700" as const },
  heading: { fontSize: 18, lineHeight: 24, fontWeight: "600" as const },
  body: { fontSize: 16, lineHeight: 22 },
  small: { fontSize: 14, lineHeight: 20 },
  caption: { fontSize: 13, lineHeight: 18 },
};

/** Android's minimum touch target is 48 x 48 dp. */
export const TOUCH = 48;
