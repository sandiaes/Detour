// Design tokens (ADR 021, docs/design.md). Modern, clean and calm: a near-white page, deep navy text, a muted
// teal as the primary accent and a restrained orange for map markers of places to eat and for the
// few actions that matter most. Flat surfaces separated by hairlines; cards only where a thing is
// picked up and opened (a trip's cover).
//
// Every text/background pair is checked against WCAG AA in theme.test.ts (4.5:1 for text, 3:1 for
// the borders that identify a control). Screens import these tokens; no screen defines a colour.
export const colors = {
  background: "#fcfcfb",
  surface: "#ffffff",
  surfaceMuted: "#f2f2f0",
  text: "#14243a",
  muted: "#56616c",
  primary: "#2b6b64",
  onPrimary: "#ffffff",
  primarySoft: "#e2eeeb",
  /** The restrained orange: places to eat on the map, and the most important single actions. */
  accent: "#b5511c",
  onAccent: "#ffffff",
  accentSoft: "#f9e8dc",
  /** Orange text on accentSoft (the accent itself is under 4.5:1 there). */
  accentText: "#8a3b12",
  /** Dark filled buttons ("New trip"), like the navy text. */
  ink: "#14243a",
  onInk: "#ffffff",
  /** Hairline dividers only. Never the sole identification of a control. */
  border: "#e4e4e1",
  /** Borders that identify a control (inputs, chips): at least 3:1 on the background. */
  outline: "#7a858c",
  warning: "#fff3d6",
  warningText: "#5c3d00",
  error: "#fbe6e3",
  errorText: "#8a1c13",
  link: "#1f5f8f",
  /** Map marker disc and its number: white on this. */
  marker: "#2b6b64",
  markerSelected: "#14243a",
  /** Restaurants and cafés on the map and in the day list: white on this. */
  eat: "#b5511c",
  eatSoft: "#f9e8dc",
  /** Text and icons drawn over a cover image, on its dark lower band or a scrim. */
  onImage: "#ffffff",
  /** The translucent disc behind icon buttons that sit on a cover image. */
  imageButton: "rgba(20, 36, 58, 0.55)",
  /** The darkening band under text on a cover photo. */
  scrim: "rgba(14, 24, 36, 0.62)",
  shadow: "#14243a",
};

export const spacing = { xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 8, md: 14, lg: 20, pill: 999 };

export const type = {
  display: { fontSize: 30, lineHeight: 36, fontWeight: "700" as const, letterSpacing: -0.3 },
  title: { fontSize: 22, lineHeight: 28, fontWeight: "700" as const },
  heading: { fontSize: 18, lineHeight: 24, fontWeight: "600" as const },
  body: { fontSize: 16, lineHeight: 22 },
  small: { fontSize: 14, lineHeight: 20 },
  caption: { fontSize: 13, lineHeight: 18 },
  /** Small capitals-like labels over metadata ("CITIES"). */
  overline: { fontSize: 12, lineHeight: 16, fontWeight: "600" as const, letterSpacing: 0.4 },
};

/** Subtle elevation for cards and the bottom bar. Android uses `elevation`, iOS the shadow keys. */
export const shadow = {
  card: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  raised: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.12,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
};

/** Line icons: one stroke width everywhere. */
export const icon = { size: 22, small: 18, large: 28, stroke: 1.8 };

/** Android's minimum touch target is 48 x 48 dp. */
export const TOUCH = 48;
