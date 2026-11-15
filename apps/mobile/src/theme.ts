import { StyleSheet } from "react-native";

// Design tokens (docs/design.md, section 2; ADR 021, decisions 78 to 90). One source for every
// colour, type size, space, radius, border, shadow, icon size and control height in the app. Screens
// and components import these; none defines a value of its own (a test in `styleTokens.test.ts`
// fails when one does, apart from the documented exceptions).
//
// Every text/background pair is checked against WCAG AA in theme.test.ts (4.5:1 for text, 3:1 for
// the borders that identify a control).

export const colors = {
  /** The page: near white (ADR 021, decision 25). */
  background: "#fcfcfb",
  /** Cards, sheets, fields, controls drawn over the page. */
  surface: "#ffffff",
  /** Quiet fills: a pressed row, a default value, a neutral badge. */
  surfaceMuted: "#f2f2f0",
  text: "#14243a",
  muted: "#56616c",
  /** Deep green: the main action, every selected state, links to the next step, sights. */
  primary: "#2b6b64",
  primaryPressed: "#225650",
  onPrimary: "#ffffff",
  primarySoft: "#e2eeeb",
  /** The selected state of tabs, chips, segments, day pills, radios, checks and the calendar. */
  selected: "#2b6b64",
  selectedSoft: "#e2eeeb",
  /** The restrained orange: places to eat. */
  accent: "#b5511c",
  onAccent: "#ffffff",
  accentSoft: "#f9e8dc",
  /** Orange text on accentSoft (the accent itself is under 4.5:1 there). */
  accentText: "#8a3b12",
  /** Navy: transport markers and the selected map marker (text uses `text`). */
  ink: "#14243a",
  onInk: "#ffffff",
  /** Hairline dividers only. Never the sole identification of a control. */
  border: "#e4e4e1",
  /** Borders that identify a control (inputs, chips, outlined buttons): at least 3:1. */
  outline: "#7a858c",
  /** Destructive actions: the confirming button, a danger row's icon and words. */
  danger: "#b42318",
  onDanger: "#ffffff",
  dangerSoft: "#fbe6e3",
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
  /** Icons and text drawn over a cover image. */
  onImage: "#ffffff",
  /** The translucent disc behind icon buttons that sit on a cover image. */
  imageButton: "rgba(20, 36, 58, 0.55)",
  /** The darker ground of a photo credit opened on the image. */
  imageOverlay: "rgba(20, 36, 58, 0.86)",
  /** The cover's soft top and bottom gradient (a colour; the gradient sets the opacity). */
  scrim: "#0d1828",
  /** The shadow under white text on a photo. */
  textShadow: "rgba(13, 24, 40, 0.55)",
  /** Tags, the attribution and buttons drawn over a map. */
  mapOverlay: "rgba(255, 255, 255, 0.94)",
  /** Behind a sheet. */
  backdrop: "rgba(20, 36, 58, 0.35)",
  shadow: "#14243a",
};

/** The tinted tile behind a document's kind: the icon colour on its soft ground, each pair checked
 * in theme.test.ts. The kind is always said in words beside it. */
export const docTones = {
  ticket: { bg: "#e2eeeb", fg: "#2b6b64" },
  booking: { bg: "#f9e8dc", fg: "#8a3b12" },
  transport: { bg: "#e2ecf6", fg: "#1f5f8f" },
  other: { bg: "#f2f2f0", fg: "#56616c" },
} as const;

/** One colour per day of a past trip, with its soft tone (ADR 021, decision 88). White text on each
 * is at least 4.5:1 and each is at least 3:1 on its tone (theme.test.ts). They repeat after eight
 * days; every use also says the day in words. */
export const dayTones = [
  { fg: "#2b6b64", bg: "#e6edec" },
  { fg: "#b35f1d", bg: "#f6ece4" },
  { fg: "#3b6fd4", bg: "#e7eefa" },
  { fg: "#8a52c4", bg: "#f1eaf8" },
  { fg: "#c8447a", bg: "#f8e9ef" },
  { fg: "#5f6d1f", bg: "#ecede4" },
  { fg: "#c4443a", bg: "#f8e9e7" },
  { fg: "#18707f", bg: "#e3eef0" },
] as const;

/** The spacing scale. Screen gutter `layout.gutter`; no component sets its own outer margin. */
export const spacing = { xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };

export const layout = {
  /** Left and right padding of every screen and sheet. */
  gutter: spacing.lg,
  /** Between sections of a screen. */
  section: spacing.xl,
  /** Between the parts of one section. */
  block: spacing.md,
};

/** Corner radii: controls 12, cards 16, sheets 24, pills fully round. */
export const radius = { xs: 6, sm: 8, md: 12, lg: 16, xl: 24, pill: 999 };

export const border = { hairline: StyleSheet.hairlineWidth, thin: 1, thick: 2 };

/** The type scale (docs/design.md, section 2). */
export const type = {
  /** The name on a trip's or a place's cover. */
  hero: { fontSize: 26, lineHeight: 32, fontWeight: "700" as const, letterSpacing: -0.2 },
  /** A screen's title. */
  title: { fontSize: 24, lineHeight: 30, fontWeight: "700" as const, letterSpacing: -0.2 },
  /** Section titles, compact header titles, sheet titles, state titles. */
  headline: { fontSize: 18, lineHeight: 24, fontWeight: "600" as const },
  /** A card's or a main row's title. */
  cardTitle: { fontSize: 16, lineHeight: 22, fontWeight: "600" as const },
  /** Paragraphs, input text, regular button labels. */
  body: { fontSize: 15, lineHeight: 21 },
  /** List titles, compact button labels, field values. */
  label: { fontSize: 14, lineHeight: 20 },
  /** Metadata, field labels, hints, chips. */
  caption: { fontSize: 13, lineHeight: 18 },
  /** Bottom-bar labels, badges, the map attribution, numbers in markers. */
  micro: { fontSize: 12, lineHeight: 16 },
};

/** Font weights by role. */
export const weight = {
  regular: "400" as const,
  medium: "500" as const,
  semibold: "600" as const,
  bold: "700" as const,
};

/** Drawn heights of controls. Touch targets reach 48 dp with `touchSlop`. */
export const size = {
  /** Buttons, inputs, selects, segmented controls. */
  control: 44,
  /** Compact buttons, chips, icon buttons in headers. */
  controlSm: 36,
  /** A row with a detail line. */
  row: 56,
  /** A one-line row, an option of a list. */
  rowCompact: 48,
  /** Underlined tabs. */
  tab: 44,
  tabCompact: 40,
  /** Number discs in lists and markers on maps. */
  mark: 24,
  marker: 26,
  markerSelected: 34,
  /** Thumbnails and tiles beside a row. */
  thumb: 56,
  tile: 40,
  /** The round "i" of a photo credit, and of the map attribution. */
  creditButton: 24,
  attributionButton: 28,
  /** A line of link text in the attribution. */
  link: 20,
  /** The portrait thumbnail of a picture document. */
  thumbPortrait: 52,
  /** The icon circle of a loading, empty or error view. */
  stateMark: 48,
  /** The drawn box of a radio mark and of a check box. */
  radio: 20,
  /** A compact header's minimum height. */
  header: 52,
  /** A multi-line field: three lines of text. */
  multiline: 72,
};

/** Android's minimum touch target is 48 x 48 dp. */
export const TOUCH = 48;

/** The hit slop that lifts a control drawn `height` tall to a 48 dp touch target. */
export function touchSlop(height: number, sides = 0) {
  const v = Math.max(0, Math.ceil((TOUCH - height) / 2));
  return { top: v, bottom: v, left: sides, right: sides };
}

/** Line icons: four sizes, one stroke width everywhere. */
export const icon = { xs: 14, sm: 16, md: 20, lg: 24, stroke: 1.8 };

/** Opacity of a pressed or disabled control (the label of a disabled one keeps its contrast in the
 * words read aloud: the state is announced). */
export const opacity = { pressed: 0.8, disabled: 0.5 };

/** Elevation: flat by default; `card` for cards and floating map controls; `raised` for sheets. */
export const shadow = {
  card: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  // A control floating over a map. No Android `elevation`: it draws a hard dark disc under a round
  // button on top of a map. A thin border says where the control ends instead.
  floating: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.1,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    borderWidth: border.thin,
    borderColor: colors.border,
  },
  raised: {
    shadowColor: colors.shadow,
    shadowOpacity: 0.12,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
};

/** White text on a photo: the shadow keeps it readable on any photo. */
export const textOnImage = {
  color: colors.onImage,
  textShadowColor: colors.textShadow,
  textShadowRadius: 6,
  textShadowOffset: { width: 0, height: 1 },
};

/** The card: a white rounded box with a hairline and a soft shadow, for a thing that is picked up
 * and opened (a proposal, a way to add a document, the file being added). */
export const card = {
  backgroundColor: colors.surface,
  borderRadius: radius.lg,
  borderWidth: border.hairline,
  borderColor: colors.border,
  ...shadow.card,
};
