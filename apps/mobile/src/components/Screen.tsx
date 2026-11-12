import type { ReactNode } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { colors } from "../theme";

type Props = { title: string; children?: ReactNode };

export function Screen({ title, children }: Props) {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
      {children}
    </ScrollView>
  );
}

export function Placeholder({ phase, text }: { phase: string; text: string }) {
  return (
    <View style={styles.placeholder}>
      <Text style={styles.body}>{text}</Text>
      <Text style={styles.muted}>Placeholder screen. Built in {phase}.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  title: { fontSize: 24, fontWeight: "700", color: colors.text },
  placeholder: { gap: 6 },
  body: { fontSize: 16, color: colors.text },
  muted: { fontSize: 13, color: colors.muted },
});
