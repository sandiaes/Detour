import { Linking, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { Button } from "../components/Button";
import { Screen } from "../components/Screen";
import { colors } from "../theme";

export function SettingsScreen() {
  const { state, apiUrl, retry } = useBackend();

  return (
    <Screen title="Settings">
      <View style={styles.section}>
        <Text style={styles.heading}>Backend</Text>
        <Text style={styles.row}>Address: {apiUrl || "not set in this build"}</Text>
        {state.phase === "connecting" ? (
          <Text style={styles.row}>
            Status: {state.waking ? "waking the server (about a minute)…" : "connecting…"}
          </Text>
        ) : null}
        {state.phase === "error" ? (
          <>
            <Text style={styles.row}>Status: not connected</Text>
            <Text style={styles.row}>{state.message}</Text>
          </>
        ) : null}
        {state.phase === "ready" ? (
          <>
            <Text style={styles.row}>Status: connected</Text>
            <Text style={styles.row}>
              Server: {state.connection.health.service} {state.connection.health.version}
              {state.connection.health.release
                ? ` (${state.connection.health.release.slice(0, 7)})`
                : ""}
            </Text>
            <Text style={styles.row}>
              Installation: {state.connection.installationId.slice(0, 8)}…
              {state.connection.registered ? " (new)" : ""}
            </Text>
          </>
        ) : null}
        <Button label="Check again" onPress={retry} />
      </View>

      {state.phase === "ready" ? (
        <View style={styles.section}>
          <Text style={styles.heading}>Map credits</Text>
          {state.connection.config.map.attribution.map((line) => (
            <Text
              key={line.url}
              style={styles.link}
              accessibilityRole="link"
              onPress={() => void Linking.openURL(line.url)}
            >
              {line.text}
            </Text>
          ))}
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { gap: 6 },
  heading: { fontSize: 18, fontWeight: "600", color: colors.text },
  row: { fontSize: 14, color: colors.text },
  link: { fontSize: 14, color: colors.link, textDecorationLine: "underline" },
});
