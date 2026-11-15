import { type ComponentRef, type ReactNode, useEffect, useRef } from "react";
import { AccessibilityInfo, StyleSheet, Text, View, findNodeHandle } from "react-native";

import { colors, layout, spacing, type } from "../../theme";
import { IconButton } from "./primitives";

// Headers (docs/design.md, "Headers"). Two, with fixed roles:
// - ScreenHeader: a page of its own (a root tab, settings, a form that starts something): Back on a
//   slim row, then the title at 24 pt and an optional subtitle.
// - CompactHeader: a screen inside a trip or over a map: Back, the title at 18 pt on one line, an
//   optional subtitle and actions, in one 52 dp row.
// Covers (a trip's, a place's) carry their own title on the photo with `CoverBar` for Back and the
// menu. Every header's title is announced when the screen appears.

/** Moves the screen reader to the element when the screen appears (a screen change). */
export function useAnnounceOnMount() {
  const ref = useRef<ComponentRef<typeof View>>(null);
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        const node = ref.current ? findNodeHandle(ref.current) : null;
        if (node) AccessibilityInfo.setAccessibilityFocus(node);
      } catch {
        // Focus is a nicety; a failure must never break a screen.
      }
    }, 200);
    return () => clearTimeout(id);
  }, []);
  return ref;
}

export function ScreenHeader({
  title,
  subtitle,
  onBack,
  right,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: ReactNode;
}) {
  const ref = useAnnounceOnMount();
  return (
    <View style={styles.header}>
      {onBack || right ? (
        <View style={styles.headerTop}>
          {onBack ? (
            <View style={styles.back}>
              <IconButton icon="back" label="Back" size="sm" onPress={onBack} />
            </View>
          ) : (
            <View />
          )}
          {right}
        </View>
      ) : null}
      <View ref={ref} accessible accessibilityRole="header" accessibilityLabel={title}>
        <Text style={styles.headerTitle}>{title}</Text>
      </View>
      {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

export function CompactHeader({
  title,
  subtitle,
  onBack,
  right,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  right?: ReactNode;
}) {
  const ref = useAnnounceOnMount();
  return (
    <View style={styles.compact}>
      {onBack ? <IconButton icon="back" label="Back" size="sm" onPress={onBack} /> : null}
      <View
        ref={ref}
        style={[styles.compactText, !onBack && styles.compactTextAlone]}
        accessible
        accessibilityRole="header"
        accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      >
        <Text style={styles.compactTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.compactSubtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right ?? null}
    </View>
  );
}

/** Back and an optional action over a cover photo, below the status bar. */
export function CoverBar({
  top,
  onBack,
  right,
}: {
  /** The status bar's height. */
  top: number;
  onBack: () => void;
  right?: ReactNode;
}) {
  return (
    <View style={[styles.coverBar, { paddingTop: top + spacing.xs }]}>
      <IconButton icon="back" label="Back" variant="onImage" onPress={onBack} />
      {right ?? null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: layout.gutter,
    paddingTop: spacing.xs,
    paddingBottom: spacing.md,
    gap: spacing.xxs,
  },
  headerTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.xs,
  },
  // The arrow lines up with the gutter.
  back: { marginLeft: -spacing.sm },
  headerTitle: { ...type.title, color: colors.text },
  headerSubtitle: { ...type.caption, color: colors.muted },

  compact: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    minHeight: 52,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  compactText: { flex: 1 },
  compactTextAlone: { paddingHorizontal: spacing.sm },
  compactTitle: { ...type.headline, color: colors.text },
  compactSubtitle: { ...type.caption, color: colors.muted },

  coverBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.sm,
  },
});
