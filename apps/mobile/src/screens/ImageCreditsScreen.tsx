import type { Photo } from "@detour/shared";
import { Linking, ScrollView, StyleSheet, Text, View } from "react-native";

import { Icon, ListRow, RowGroup, ScreenHeader } from "../components/ds";
import { useData } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";

/** Every photo inside a value the backend sent (a trip list, an itinerary…), each once, by id. */
export function collectPhotos(values: Iterable<unknown>): Photo[] {
  const found = new Map<string, Photo>();
  const visit = (value: unknown, depth: number) => {
    if (depth > 8 || value === null || typeof value !== "object") return;
    if (Array.isArray(value)) {
      for (const v of value) visit(v, depth + 1);
      return;
    }
    const obj = value as Record<string, unknown>;
    const credit = obj.credit as Record<string, unknown> | undefined;
    if (
      typeof obj.id === "string" &&
      typeof obj.url === "string" &&
      obj.url.startsWith("/v1/images/") &&
      credit &&
      typeof credit.author === "string"
    ) {
      found.set(obj.id, obj as unknown as Photo);
      return;
    }
    for (const v of Object.values(obj)) visit(v, depth + 1);
  };
  for (const v of values) visit(v, 0);
  return [...found.values()].sort(
    (a, b) => a.credit.author.localeCompare(b.credit.author) || a.id.localeCompare(b.id),
  );
}

/**
 * Image credits (ADR 022, decision 20): author, licence and a link for every photo the app holds
 * now (the trips and plans it has loaded). Each photo also carries its own credit behind its "i".
 */
export function ImageCreditsScreen() {
  const nav = useNavigation();
  const data = useData();
  const photos = collectPhotos([...data.memory.values()].map((e) => e.data));
  return (
    <View style={styles.fill}>
      <ScreenHeader title="Image credits" onBack={nav.back} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.intro}>
          <Text style={styles.text}>
            Photos come from Wikimedia Commons and are shown resized. These are the photos of the
            trips and plans open in the app.
          </Text>
          {photos.length === 0 ? (
            <Text style={styles.text}>No photo has been shown yet.</Text>
          ) : null}
        </View>
        {photos.length > 0 ? (
          <RowGroup>
            {photos.map((p) => (
              <ListRow
                key={p.id}
                title={p.credit.author}
                detail={`${p.credit.licence} · ${decodeName(p.credit.source_url)}`}
                accessibilityLabel={`${p.credit.text}. Opens the photo's page on Wikimedia Commons.`}
                trailing={<Icon name="external" size="sm" color={colors.muted} />}
                onPress={() => void Linking.openURL(p.credit.source_url)}
                testID={`credit-${p.id}`}
              />
            ))}
          </RowGroup>
        ) : null}
      </ScrollView>
    </View>
  );
}

function decodeName(url: string): string {
  const name = url.split("/File:")[1] ?? url;
  try {
    return decodeURIComponent(name).replace(/_/g, " ");
  } catch {
    return name;
  }
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { gap: layout.section, paddingBottom: spacing.xxl },
  intro: { paddingHorizontal: layout.gutter, gap: spacing.sm },
  text: { ...type.label, color: colors.muted },
});
