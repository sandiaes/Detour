import type { Photo } from "@detour/shared";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Icon } from "../components/ds/Icon";
import { ScreenHeader } from "../components/ui";
import { useData } from "../data/DataProvider";
import { useNavigation } from "../nav/Navigator";
import { colors, spacing, type } from "../theme";

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
        <Text style={styles.intro}>
          Photos come from Wikimedia Commons and are shown resized. These are the photos of the
          trips and plans open in the app.
        </Text>
        {photos.length === 0 ? (
          <Text style={styles.intro}>No photo has been shown yet.</Text>
        ) : (
          photos.map((p) => (
            <Pressable
              key={p.id}
              accessibilityRole="link"
              accessibilityLabel={`${p.credit.text}. Opens the photo's page on Wikimedia Commons.`}
              onPress={() => void Linking.openURL(p.credit.source_url)}
              style={styles.row}
              testID={`credit-${p.id}`}
            >
              <View style={styles.rowText}>
                <Text style={styles.author}>{p.credit.author}</Text>
                <Text style={styles.meta}>
                  {p.credit.licence} · {decodeName(p.credit.source_url)}
                </Text>
              </View>
              <Icon name="export" size={16} color={colors.muted} />
            </Pressable>
          ))
        )}
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
  content: { padding: spacing.lg, gap: spacing.sm },
  intro: { ...type.small, color: colors.muted },
  row: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  rowText: { flex: 1, gap: 2 },
  author: { ...type.small, color: colors.text, fontWeight: "600" },
  meta: { ...type.caption, color: colors.muted },
});
