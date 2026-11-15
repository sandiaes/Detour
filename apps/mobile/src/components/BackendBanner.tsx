import { StyleSheet, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { layout, spacing } from "../theme";
import { Notice } from "./ds";

/** Shown above every screen while the backend is not ready. Hidden once it is. */
export function BackendBanner() {
  const { state, retry } = useBackend();
  if (state.phase === "ready") return null;
  return (
    <View style={styles.banner}>
      {state.phase === "connecting" ? (
        <Notice tone="warning" label={state.waking ? "Waking the server" : "Connecting"}>
          {state.waking
            ? "The free host was asleep and is starting up."
            : "Connecting to the server…"}
        </Notice>
      ) : (
        <Notice tone="error" label="Offline" action={{ label: "Retry", onPress: retry }}>
          Could not reach the server. {state.message}
          {state.retryAt ? " Trying again by itself; saved trips can still be read." : ""}
        </Notice>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { paddingHorizontal: layout.gutter, paddingVertical: spacing.xs },
});
