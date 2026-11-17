import { StyleSheet, Text, View } from "react-native";

import { useBackend, useOffline } from "../api/BackendProvider";
import { colors, layout, radius, spacing, type, weight } from "../theme";
import { Icon, Notice } from "./ds";

/**
 * Shown above every screen while the backend is not ready. Offline is one quiet message; it is the
 * only offline message in the app (screens do not repeat it).
 */
export function BackendBanner() {
  const { state } = useBackend();
  const offline = useOffline();
  if (state.phase === "connecting" && !offline) {
    return (
      <View style={styles.banner}>
        <Notice tone="warning" label={state.waking ? "Waking the server" : "Connecting"}>
          {state.waking
            ? "The free host was asleep and is starting up."
            : "Connecting to the server…"}
        </Notice>
      </View>
    );
  }
  if (!offline) return null;
  return (
    <View style={styles.banner}>
      <View style={styles.offline} accessibilityLiveRegion="polite" testID="offline-banner">
        <Icon name="offline" size="md" color={colors.errorText} />
        <View style={styles.text}>
          <Text style={styles.title}>You’re offline</Text>
          <Text style={styles.body}>Saved trips remain available.</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { paddingHorizontal: layout.gutter, paddingVertical: spacing.xs },
  offline: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.error,
  },
  text: { flex: 1 },
  title: { ...type.label, color: colors.text, fontWeight: weight.bold },
  body: { ...type.caption, color: colors.muted },
});
