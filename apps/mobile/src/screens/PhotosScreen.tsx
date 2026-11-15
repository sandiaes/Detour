import { ScrollView, StyleSheet, View } from "react-native";

import { PlannedFeature, ScreenHeader } from "../components/ds";
import { layout } from "../theme";

/**
 * Photos across all trips (ADR 021). Not built: photos grouped by day or place need storage and,
 * for device photos or Google Photos, a permission or an integration with its own ADR.
 */
export function PhotosScreen() {
  return (
    <View style={styles.fill}>
      <ScreenHeader title="Photos" />
      <ScrollView contentContainerStyle={styles.content}>
        <PlannedFeature
          icon="photos"
          title="Trip photos are planned"
          text="Your photos, grouped by trip, day and place, will appear here. Adding photos from the device or from Google Photos is not built yet."
          testID="photos-planned"
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingHorizontal: layout.gutter },
});
