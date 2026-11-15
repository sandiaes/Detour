import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "../../theme";

// Overlays drawn on a map: a status tag ("Loading the map…") at the top left. Buttons on a map are
// `IconButton variant="onMap"`; the key and the panels are white cards (`card`).

export function MapChip({ text, live = false }: { text: string; live?: boolean }) {
  return (
    <View style={styles.chip} accessibilityLiveRegion={live ? "polite" : undefined}>
      <Text style={styles.text}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    position: "absolute",
    top: spacing.sm,
    left: spacing.sm,
    backgroundColor: colors.mapOverlay,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  text: { ...type.caption, color: colors.text },
});
