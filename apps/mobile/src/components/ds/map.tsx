import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "../../theme";
import { Button } from "./Button";
import { Notice } from "./states";

// Overlays drawn on a map (docs/design.md, "Components"): a status tag at the top left (`MapChip`),
// a white panel for the key (`MapPanel`) and the failure message with its two ways out
// (`MapFailure`). A button on a map is `IconButton variant="onMap"`.

export function MapChip({ text, live = false }: { text: string; live?: boolean }) {
  return (
    <View style={styles.chip} accessibilityLiveRegion={live ? "polite" : undefined}>
      <Text style={styles.text}>{text}</Text>
    </View>
  );
}

/** A white panel over a map: the key. Radius 16, the card shadow. */
export function MapPanel({ children }: { children: ReactNode }) {
  return (
    <View style={styles.panel} accessibilityLiveRegion="polite">
      {children}
    </View>
  );
}

/** The map could not load: what happened, "Try the map again" and a way to the list. */
export function MapFailure({
  message,
  onRetry,
  listLabel,
  onShowList,
}: {
  message: string;
  onRetry: () => void;
  listLabel: string;
  onShowList: () => void;
}) {
  return (
    <View style={styles.failure}>
      <Notice tone="error" action={{ label: "Try the map again", onPress: onRetry }}>
        {message}
      </Notice>
      <Button label={listLabel} variant="secondary" size="sm" onPress={onShowList} />
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
  panel: {
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadow.card,
  },
  failure: {
    position: "absolute",
    top: spacing.md,
    left: spacing.md,
    right: spacing.md,
    gap: spacing.sm,
    alignItems: "flex-start",
  },
});
