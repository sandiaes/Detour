import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { colors } from "../theme";
import { Button } from "./Button";

/** Shown above every screen while the backend is not ready. Hidden once it is. */
export function BackendBanner() {
  const { state, retry } = useBackend();
  if (state.phase === "ready") return null;

  if (state.phase === "connecting") {
    return (
      <View style={[styles.banner, styles.warning]} accessibilityLiveRegion="polite">
        <Text style={styles.text}>
          {state.waking
            ? "Waking the server. The free host was asleep."
            : "Connecting to the server…"}
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.banner, styles.error]} accessibilityLiveRegion="polite">
      <Text style={styles.text}>Could not reach the server. {state.message}</Text>
      <Button label="Retry" onPress={retry} />
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { padding: 12, gap: 8 },
  warning: { backgroundColor: colors.warning },
  error: { backgroundColor: colors.error },
  text: { fontSize: 14, color: colors.text },
});
