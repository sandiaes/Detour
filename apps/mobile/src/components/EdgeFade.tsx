import { StyleSheet, View } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";

import { colors } from "../theme";

/**
 * A soft edge: the page colour fading to nothing over a few dp, so scrolled content and the map
 * dissolve into the status bar's edge and the bottom bar instead of being cut by a hard line.
 * Decorative and never touchable; it takes no part in the accessibility tree.
 */
export function EdgeFade({ edge, size }: { edge: "top" | "bottom"; size: number }) {
  const id = `fade-${edge}`;
  const top = edge === "top";
  return (
    <View
      pointerEvents="none"
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      style={[styles.fade, top ? { top: 0 } : { bottom: 0 }, { height: size }]}
      testID={`edge-fade-${edge}`}
    >
      <Svg width="100%" height="100%" preserveAspectRatio="none">
        <Defs>
          <LinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={colors.background} stopOpacity={top ? 1 : 0} />
            <Stop offset="1" stopColor={colors.background} stopOpacity={top ? 0 : 1} />
          </LinearGradient>
        </Defs>
        <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${id})`} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  fade: { position: "absolute", left: 0, right: 0 },
});
