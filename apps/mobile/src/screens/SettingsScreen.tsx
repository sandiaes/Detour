import type { AttributionEntry } from "@detour/shared";
import { Linking, ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call } from "../api/unwrap";
import {
  Button,
  Icon,
  InfoRow,
  ListRow,
  RowGroup,
  ScreenHeader,
  SectionHeader,
} from "../components/ds";
import { useResource } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";

const openPage = (url: string) => void Linking.openURL(url);

export function SettingsScreen() {
  const { state, apiUrl, retry } = useBackend();
  const nav = useNavigation();
  // Credits for the data in use (OpenStreetMap, GeoNames, tiles). Saved on the device, so they
  // are still readable offline.
  const credits = useResource<AttributionEntry[]>("attributions", (c) =>
    call(c.GET("/v1/attributions")),
  );

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Settings" onBack={nav.depth > 1 ? nav.back : undefined} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.block}>
          <SectionHeader title="Connection" />
          <View>
            <InfoRow label="Address" value={apiUrl || "not set in this build"} />
            {state.phase === "connecting" ? (
              <InfoRow
                label="Status"
                value={state.waking ? "waking the server (about a minute)…" : "connecting…"}
              />
            ) : null}
            {state.phase === "error" ? (
              <>
                <InfoRow label="Status" value="not connected" />
                <InfoRow label="Problem" value={state.message} />
              </>
            ) : null}
            {state.phase === "ready" ? (
              <>
                <InfoRow label="Status" value="connected" />
                <InfoRow
                  label="Server"
                  value={`${state.connection.health.service} ${state.connection.health.version}${
                    state.connection.health.release
                      ? ` (${state.connection.health.release.slice(0, 7)})`
                      : ""
                  }`}
                />
                <InfoRow
                  label="Installation"
                  value={`${state.connection.installationId.slice(0, 8)}…${
                    state.connection.registered ? " (new)" : ""
                  }`}
                />
              </>
            ) : null}
          </View>
          <Button label="Check again" variant="secondary" size="sm" onPress={retry} />
        </View>

        <View style={styles.credits}>
          <View style={styles.block}>
            <SectionHeader title="Credits" />
            <Text style={styles.text}>
              Places, maps and place names come from open data. Please keep these credits visible.
            </Text>
          </View>
          {credits.data ? (
            <RowGroup>
              {credits.data.map((c) => (
                <ListRow
                  key={`${c.name}:${c.url}`}
                  title={c.text}
                  detail={`${c.applies_to}${c.licence ? ` · ${c.licence}` : ""}`}
                  accessibilityLabel={`${c.text}. ${c.applies_to}. Opens the page in the browser.`}
                  trailing={<Icon name="external" size="sm" color={colors.muted} />}
                  onPress={() => openPage(c.url)}
                />
              ))}
            </RowGroup>
          ) : state.phase === "ready" ? (
            <RowGroup>
              {state.connection.config.map.attribution.map((line) => (
                <ListRow
                  key={line.url}
                  title={line.text}
                  accessibilityLabel={`${line.text}. Opens the page in the browser.`}
                  trailing={<Icon name="external" size="sm" color={colors.muted} />}
                  onPress={() => openPage(line.url)}
                />
              ))}
            </RowGroup>
          ) : (
            <View style={styles.block}>
              <Text style={styles.text}>The credits load once the server is reachable.</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { gap: layout.section, paddingBottom: spacing.xxl },
  // Text sits on the gutter; rows of links run to the screen's edges.
  block: { paddingHorizontal: layout.gutter, gap: spacing.sm },
  credits: { gap: spacing.sm },
  text: { ...type.label, color: colors.text },
});
