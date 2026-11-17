import { Image, StyleSheet, Text, View } from "react-native";

import { colors, spacing, type, weight } from "../theme";
import { Icon } from "./ds";

const LOGO = require("../../assets/detour-logo.png") as number;
const LOGO_WIDTH = 200;
const LOGO_HEIGHT = Math.round((LOGO_WIDTH * 462) / 1288);
const FADED = 0.25;

/** What the map area shows when the map cannot load: the app logo, faded. It says nothing; the
 * banner at the top of the app already tells the user they are offline. */
export function OfflineMap() {
  return (
    <View style={styles.fill} testID="offline-map" importantForAccessibility="no">
      <Image
        source={LOGO}
        style={styles.logo}
        resizeMode="contain"
        accessibilityIgnoresInvertColors
      />
      <Icon name="offline" size="lg" color={colors.muted} />
      <Text style={styles.title}>You’re offline</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  title: { ...type.label, color: colors.muted, fontWeight: weight.bold },
  logo: { width: LOGO_WIDTH, height: LOGO_HEIGHT, opacity: FADED },
});
