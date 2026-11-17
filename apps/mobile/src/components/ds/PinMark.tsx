import Svg, { Circle, Path } from "react-native-svg";

import { colors, size as sizes } from "../../theme";

// The pin of the app logo (ADR 021, decision 103), drawn on the world map for the cities of the
// user's trips. Decoration: the control around it carries the spoken name.

const PIN = "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z";
const HEIGHT = { map: sizes.pin, selected: sizes.pinSelected, key: sizes.pinKey };
/** The viewBox is the pin's own box, so its tip is the bottom edge. */
const RATIO = 16 / 20;

export function PinMark({
  tone,
  size = "map",
  selected = false,
}: {
  /** "been": the logo's orange. "going": the logo's green. */
  tone: "been" | "going";
  size?: keyof typeof HEIGHT;
  selected?: boolean;
}) {
  const height = selected ? HEIGHT.selected : HEIGHT[size];
  return (
    <Svg
      width={height * RATIO}
      height={height}
      viewBox="4 2 16 20"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <Path
        d={PIN}
        fill={tone === "been" ? colors.pinBeen : colors.pinGoing}
        stroke={selected ? colors.markerSelected : colors.surface}
        strokeWidth={selected ? 1.6 : 1.2}
        strokeLinejoin="round"
      />
      <Circle cx={12} cy={10} r={2.6} fill={colors.surface} />
    </Svg>
  );
}
