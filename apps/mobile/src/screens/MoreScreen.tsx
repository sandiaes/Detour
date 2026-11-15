import { ScrollView, StyleSheet, Text, View } from "react-native";

import { ListRow, RowGroup } from "../components/ds/primitives";
import { ScreenHeader } from "../components/ui";
import { useNavigation } from "../nav/Navigator";
import { colors, spacing, type } from "../theme";

/**
 * More (ADR 021). Settings works today; the other rows are the planned parts of the design and
 * say so. A trip's own actions (new proposals, mark as past, delete) stay in its settings.
 */
export function MoreScreen() {
  const nav = useNavigation();
  return (
    <View style={styles.fill}>
      <ScreenHeader title="More" />
      <ScrollView contentContainerStyle={styles.content}>
        <RowGroup>
          <ListRow
            icon="bookmark"
            title="Saved places"
            detail="Places you keep for later trips"
            disabled
          />
          <ListRow
            icon="preferences"
            title="Travel preferences"
            detail="Pace, interests and meals"
            disabled
          />
          <ListRow
            icon="export"
            title="Back up all trips"
            detail="One file with every trip, to keep or move to a new phone"
            testID="more-backup"
            onPress={() => nav.push({ name: "exportTrips" })}
          />
          <ListRow
            icon="export"
            title="Import a trip"
            detail="Add trips from a Detour file"
            testID="more-import"
            onPress={() => nav.push({ name: "importTrips" })}
          />
          <ListRow
            icon="archive"
            title="Archive trip"
            detail="Hide a trip from your lists"
            disabled
          />
        </RowGroup>
        <RowGroup>
          <ListRow
            icon="photos"
            title="Image credits"
            detail="Author and licence of every photo"
            testID="more-image-credits"
            onPress={() => nav.push({ name: "imageCredits" })}
          />
          <ListRow
            icon="settings"
            title="Settings"
            detail="Connection, version and data credits"
            testID="more-settings"
            onPress={() => nav.push({ name: "settings" })}
          />
        </RowGroup>
        <Text style={styles.note}>
          A trip&apos;s own actions (export, new proposals, mark as past, delete) are in the
          trip&apos;s menu.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.lg },
  note: { ...type.small, color: colors.muted },
});
