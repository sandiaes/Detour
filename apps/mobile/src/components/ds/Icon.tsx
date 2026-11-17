import Svg, { Circle, Path, Rect } from "react-native-svg";

import { colors, icon as iconTokens } from "../../theme";

// Simple line icons drawn for Detour (ADR 021): a 24-unit grid, one stroke width, round ends.
// Icons are decoration: the control around them carries the spoken name, so every icon is hidden
// from screen readers.

type Shape = { d?: string[]; circles?: [number, number, number][]; rects?: number[][] };

const SHAPES = {
  trips: {
    rects: [[3, 7, 18, 13, 2]],
    d: ["M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2", "M3 12.5h18"],
  },
  explore: { circles: [[12, 12, 9]], d: ["M15.5 8.5l-2 5-5 2 2-5z"] },
  add: { d: ["M12 5v14", "M5 12h14"] },
  photos: { rects: [[3, 4, 18, 16, 2]], circles: [[8.5, 9.5, 1.6]], d: ["M21 16l-5-5-9 9"] },
  more: { d: ["M4 7h16", "M4 12h16", "M4 17h16"] },
  back: { d: ["M15 5l-7 7 7 7"] },
  chevronRight: { d: ["M9 5l7 7-7 7"] },
  up: { d: ["M6 15l6-6 6 6"] },
  down: { d: ["M6 9l6 6 6-6"] },
  dots: {
    circles: [
      [6, 12, 1.2],
      [12, 12, 1.2],
      [18, 12, 1.2],
    ],
  },
  settings: {
    circles: [
      [12, 12, 3],
      [12, 12, 7],
    ],
    d: [
      "M12 2v3",
      "M12 19v3",
      "M2 12h3",
      "M19 12h3",
      "M4.9 4.9l2.1 2.1",
      "M17 17l2.1 2.1",
      "M4.9 19.1L7 17",
      "M17 7l2.1-2.1",
    ],
  },
  calendar: { rects: [[3, 5, 18, 16, 2]], d: ["M3 10h18", "M8 3v4", "M16 3v4"] },
  pin: { d: ["M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"], circles: [[12, 10, 2.5]] },
  restaurant: { d: ["M6 3v6a3 3 0 0 0 6 0V3", "M9 3v18", "M17 3c-2 2-3 5-3 8h4V3", "M18 11v10"] },
  attraction: {
    d: ["M3 21h18", "M5 21V10", "M9.67 21V10", "M14.33 21V10", "M19 21V10", "M2.5 10L12 4l9.5 6z"],
  },
  city: {
    rects: [[4, 3, 10, 18, 1]],
    d: ["M14 9h5a1 1 0 0 1 1 1v11", "M3 21h18", "M7.5 7h3", "M7.5 11h3", "M7.5 15h3"],
  },
  document: {
    d: [
      "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z",
      "M14 3v5h5",
      "M9 13h6",
      "M9 17h6",
    ],
  },
  note: { d: ["M4 20h4L19 9l-4-4L4 16z", "M13.5 6.5l4 4"] },
  map: { d: ["M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z", "M9 4v14", "M15 6v14"] },
  list: { d: ["M8 6h13", "M8 12h13", "M8 18h13", "M3.5 6h.01", "M3.5 12h.01", "M3.5 18h.01"] },
  transport: {
    rects: [[5, 3, 14, 14, 3]],
    d: ["M5 10h14", "M8 21l2-4", "M16 21l-2-4"],
    circles: [
      [9, 13.5, 0.8],
      [15, 13.5, 0.8],
    ],
  },
  // Transport legs (ADR 032): a train is the "transport" shape; these are the other modes.
  bus: {
    rects: [[4, 3, 16, 15, 2]],
    d: ["M4 11h16", "M4 7h16", "M7 18v3", "M17 18v3"],
    circles: [
      [8, 14.5, 0.8],
      [16, 14.5, 0.8],
    ],
  },
  metro: {
    circles: [[12, 12, 9]],
    d: ["M8 16V8l4 5 4-5v8"],
  },
  ferry: {
    d: [
      "M3 19c1.5 1 3 1 4.5 0s3-1 4.5 0 3 1 4.5 0 3-1 4.5 0",
      "M5 15l-1-4h16l-1 4",
      "M7 11V7h10v4",
      "M12 7V3",
    ],
  },
  taxi: {
    d: [
      "M5 16v-4l1.8-4.6A2 2 0 0 1 8.7 6h6.6a2 2 0 0 1 1.9 1.4L19 12v4",
      "M3 16h18",
      "M5 12h14",
      "M10 3h4v3",
    ],
    circles: [
      [7.5, 17.5, 1.5],
      [16.5, 17.5, 1.5],
    ],
  },
  walk: {
    circles: [[13, 4.5, 1.8]],
    d: ["M11 21l2-6-2.5-3 1-4.5L15 10l3 1.5", "M10.5 7.5L7 10v3.5", "M13 15l3 6"],
  },
  car: {
    d: ["M5 16v-4l1.8-4.6A2 2 0 0 1 8.7 6h6.6a2 2 0 0 1 1.9 1.4L19 12v4", "M3 16h18", "M5 12h14"],
    circles: [
      [7.5, 17.5, 1.5],
      [16.5, 17.5, 1.5],
    ],
  },
  home: { d: ["M4 11l8-7 8 7", "M6 10v10h12V10", "M10 20v-6h4v6"] },
  clock: { circles: [[12, 12, 9]], d: ["M12 7v5l3 2"] },
  route: {
    circles: [
      [6, 18, 2],
      [18, 6, 2],
    ],
    d: ["M8 18h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7"],
  },
  search: { circles: [[11, 11, 6.5]], d: ["M16 16l4.5 4.5"] },
  check: { d: ["M5 12.5l4.5 4.5L19 7"] },
  close: { d: ["M6 6l12 12", "M18 6L6 18"] },
  bookmark: { d: ["M6 3h12v18l-6-4-6 4z"] },
  ticket: {
    d: [
      "M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z",
      "M14 6v12",
    ],
  },
  shield: { d: ["M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z", "M9 12l2 2 4-4"] },
  preferences: {
    d: ["M4 6h9", "M17 6h3", "M4 12h3", "M11 12h9", "M4 18h11", "M19 18h1"],
    circles: [
      [15, 6, 2],
      [9, 12, 2],
      [17, 18, 2],
    ],
  },
  export: { d: ["M12 15V3", "M8 7l4-4 4 4", "M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"] },
  archive: {
    rects: [[3, 4, 18, 5, 1]],
    d: ["M5 9v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9", "M10 13h4"],
  },
  history: { d: ["M3 12a9 9 0 1 0 3-6.7", "M3 4v5h5", "M12 8v4l3 2"] },
  info: { circles: [[12, 12, 9]], d: ["M12 11v6", "M12 7.5h.01"] },
  cafe: {
    d: [
      "M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z",
      "M16 10h1.5a2.5 2.5 0 0 1 0 5H16",
      "M7 3c-.8 1 .8 1.6 0 2.6",
      "M11 3c-.8 1 .8 1.6 0 2.6",
      "M3 21h14",
    ],
  },
  sight: {
    circles: [[8, 6, 2]],
    d: ["M8 9v5l-2.5 6", "M8 14l3 6", "M5 11l3-1 3 1", "M14 21V9l4-3 3 3v12", "M14 21h7"],
  },
  lock: { rects: [[5, 11, 14, 10, 2]], d: ["M8 11V8a4 4 0 0 1 8 0v3"] },
  unlock: { rects: [[5, 11, 14, 10, 2]], d: ["M8 11V8a4 4 0 0 1 7.5-2"] },
  refresh: { d: ["M20 12a8 8 0 1 1-2.5-5.8", "M20 4v5h-5"] },
  trash: { d: ["M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 13h10l1-13", "M9 7V4h6v3"] },
  minus: { d: ["M5 12h14"] },
  import: { d: ["M12 3v12", "M8 11l4 4 4-4", "M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"] },
  external: {
    d: ["M14 4h6v6", "M20 4l-9 9", "M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"],
  },
  offline: {
    d: [
      "M2 8.8a15 15 0 0 1 20 0",
      "M5 12.5a10.5 10.5 0 0 1 14 0",
      "M8.5 16a5.5 5.5 0 0 1 7 0",
      "M12 19.5h.01",
      "M3 3l18 18",
    ],
  },
  alert: { d: ["M12 4L2.5 20h19z", "M12 10v4.5", "M12 17.5h.01"] },
} satisfies Record<string, Shape>;

export type IconName = keyof typeof SHAPES;
export const ICON_NAMES = Object.keys(SHAPES) as IconName[];

/** The four icon sizes (docs/design.md): xs 14 in metadata, sm 16 in rows and compact controls,
 * md 20 in regular controls, lg 24 in the bottom bar and on covers. A number is for an illustration
 * only (the empty Documents tab, a tile scaled to its box). */
export type IconSize = "xs" | "sm" | "md" | "lg";

export function iconSize(size: IconSize | number): number {
  return typeof size === "number" ? size : iconTokens[size];
}

export function Icon({
  name,
  size = "md",
  color = colors.text,
}: {
  name: IconName;
  size?: IconSize | number;
  color?: string;
}) {
  const shape: Shape = SHAPES[name];
  const px = iconSize(size);
  const strokeWidth = iconTokens.stroke;
  const dotFill = name === "dots" ? color : "none";
  return (
    <Svg
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      testID={`icon-${name}`}
    >
      {shape.rects?.map(([x, y, w, h, r], i) => (
        <Rect key={`r${i}`} x={x} y={y} width={w} height={h} rx={r} />
      ))}
      {shape.circles?.map(([cx, cy, r], i) => (
        <Circle key={`c${i}`} cx={cx} cy={cy} r={r} fill={dotFill} />
      ))}
      {shape.d?.map((d, i) => (
        <Path key={`p${i}`} d={d} />
      ))}
    </Svg>
  );
}
