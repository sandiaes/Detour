import { useEffect, useRef, useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { colors } from "../theme";

// OSMF attribution guidelines: the credit must be visible without interaction at first. It may
// collapse after five seconds or on map interaction if it can be found again, here by an "i"
// button. Spike S1 found the credit collapsing at once on the map's own initial camera move, so
// only a real user gesture (counted by `userInteractionCount`) collapses it early.
export const COLLAPSE_AFTER_MS = 5000;

export type AttributionLine = { text: string; url: string };

type Props = {
  lines: AttributionLine[];
  /** Increase this number each time the user moves the map. */
  userInteractionCount?: number;
  /** Extra distance from the bottom edge, for a map whose lower edge is covered by a sheet. */
  bottomOffset?: number;
};

export function AttributionBar({ lines, userInteractionCount = 0, bottomOffset = 0 }: Props) {
  const [expanded, setExpanded] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCount = useRef(userInteractionCount);

  const startTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setExpanded(false), COLLAPSE_AFTER_MS);
  };

  useEffect(() => {
    startTimer();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  useEffect(() => {
    if (userInteractionCount !== lastCount.current) {
      lastCount.current = userInteractionCount;
      if (timer.current) clearTimeout(timer.current);
      setExpanded(false);
    }
  }, [userInteractionCount]);

  if (!expanded) {
    return (
      <Pressable
        style={[styles.infoButton, { bottom: 8 + bottomOffset }]}
        accessibilityRole="button"
        accessibilityLabel="Show map attribution"
        hitSlop={12}
        onPress={() => {
          setExpanded(true);
          startTimer();
        }}
      >
        <Text style={styles.infoButtonText}>i</Text>
      </Pressable>
    );
  }

  return (
    <View style={[styles.bar, { bottom: 8 + bottomOffset }]} accessibilityLabel="Map attribution">
      {lines.map((line) => (
        <Pressable
          key={line.url}
          accessibilityRole="link"
          accessibilityLabel={line.text}
          hitSlop={{ top: 14, bottom: 14, left: 4, right: 4 }}
          style={styles.linkTarget}
          onPress={() => void Linking.openURL(line.url)}
        >
          <Text style={styles.link}>{line.text}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    position: "absolute",
    left: 8,
    bottom: 8,
    flexDirection: "row",
    flexWrap: "wrap",
    maxWidth: "75%",
    paddingHorizontal: 6,
    paddingVertical: 4,
    backgroundColor: "rgba(255,255,255,0.9)",
    borderRadius: 4,
  },
  // 20 dp of text line plus 14 dp of hit slop above and below: a 48 dp touch target.
  linkTarget: { minHeight: 20, justifyContent: "center" },
  link: { fontSize: 12, color: colors.link, textDecorationLine: "underline", marginRight: 6 },
  infoButton: {
    position: "absolute",
    left: 8,
    bottom: 8,
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.9)",
    borderWidth: 1,
    borderColor: "#666666",
  },
  infoButtonText: { fontSize: 16, fontWeight: "700", color: colors.text },
});
