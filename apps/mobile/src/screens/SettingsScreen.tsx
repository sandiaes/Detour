import type { AttributionEntry } from "@detour/shared";
import { Linking, ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call } from "../api/unwrap";
import { Button } from "../components/Button";
import { ScreenHeader } from "../components/ui";
import { useResource } from "../data/DataProvider";
import { colors, spacing, type } from "../theme";

function CreditLink({ text, url }: { text: string; url: string }) {
  return (
    <Text
      style={styles.link}
      accessibilityRole="link"
      accessibilityHint="Opens the page in the browser"
      onPress={() => void Linking.openURL(url)}
    >
      {text}
    </Text>
  );
}

export function SettingsScreen() {
  const { state, apiUrl, retry } = useBackend();
  // Credits for the data in use (OpenStreetMap, GeoNames, tiles). Saved on the device, so they
  // are still readable offline.
  const credits = useResource<AttributionEntry[]>("attributions", (c) =>
    call(c.GET("/v1/attributions")),
  );

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Settings" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.section}>
          <Text accessibilityRole="header" style={styles.heading}>
            Connection
          </Text>
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
          <Button label="Check again" variant="secondary" onPress={retry} />
        </View>

        <View style={styles.section}>
          <Text accessibilityRole="header" style={styles.heading}>
            Credits
          </Text>
          <Text style={styles.row}>
            Places, maps and place names come from open data. Please keep these credits visible.
          </Text>
          {credits.data ? (
            credits.data.map((c) => (
              <View key={`${c.name}:${c.url}`} style={styles.credit}>
                <CreditLink text={c.text} url={c.url} />
                <Text style={styles.creditMeta}>
                  {c.applies_to}
                  {c.licence ? ` · ${c.licence}` : ""}
                </Text>
              </View>
            ))
          ) : state.phase === "ready" ? (
            state.connection.config.map.attribution.map((line) => (
              <CreditLink key={line.url} text={line.text} url={line.url} />
            ))
          ) : (
            <Text style={styles.row}>The credits load once the server is reachable.</Text>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.xl },
  section: { gap: spacing.sm },
  heading: { ...type.heading, color: colors.text },
  row: { ...type.small, color: colors.text },
  link: {
    ...type.small,
    color: colors.link,
    textDecorationLine: "underline",
    minHeight: 48,
    textAlignVertical: "center",
  },
  credit: { gap: 2 },
  creditMeta: { ...type.caption, color: colors.muted },
});
