import { ScrollView, StyleSheet, View } from "react-native";

import { PlannedFeature } from "../components/ds/primitives";
import { ScreenHeader } from "../components/ui";
import { spacing } from "../theme";

/**
 * Explore (ADR 021): a place in the navigation for finding places outside a trip. Not built: it
 * would need a product decision on what is searched and shown, and no new provider may be added
 * without an ADR. Places are added from inside a trip for now.
 */
export function ExploreScreen() {
  return (
    <View style={styles.fill}>
      <ScreenHeader title="Explore" />
      <ScrollView contentContainerStyle={styles.content}>
        <PlannedFeature
          icon="explore"
          title="Explore is planned"
          text="Browsing places to visit outside a trip is not built yet. To add a sight or a restaurant now, open a trip and use Add."
          testID="explore-planned"
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { padding: spacing.lg },
});
