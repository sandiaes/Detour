import type { Photo } from "@detour/shared";
import { type ReactNode, useContext, useState } from "react";
import { Image, Linking, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from "react-native-svg";

import { BackendContext } from "../../api/BackendProvider";
import { colors, radius, spacing, type as typeScale } from "../../theme";
import { Icon } from "./Icon";

// A destination's or place's cover (ADR 021, ADR 022). A photo appears only when the backend sent
// one (`photo`: Wikimedia Commons, served through the backend); otherwise nothing is invented and
// the cover is a calm illustrated landscape whose colours and hills are chosen from the
// destination identifier, so a trip always looks the same. A cover has no dark band or scrim: text
// goes beside it, not over it. A photo has its average colour behind it while it loads, and its
// credit sits behind a small "i" in its bottom right corner (`PhotoCredit`, drawn by `Cover`).

/** The `mid` and `near` colours are the hills; white on both is checked at 4.5:1 (theme.test.ts)
 * for the controls drawn on a cover. */
export const COVER_TONES = [
  { sky: "#cfe3df", haze: "#eef4f1", far: "#8fb4ad", mid: "#3f6f68", near: "#264e49" },
  { sky: "#f1d8c3", haze: "#faeee3", far: "#d0a68c", mid: "#7a5040", near: "#4f3326" },
  { sky: "#d3e0ec", haze: "#eef3f8", far: "#93abc0", mid: "#46627c", near: "#26394c" },
  { sky: "#dfe7d2", haze: "#f2f5ec", far: "#a3b593", mid: "#4f6744", near: "#2f432b" },
  { sky: "#eee3cc", haze: "#f8f3e8", far: "#c8b089", mid: "#6e5a3a", near: "#4a3c24" },
] as const;

const RIDGES = [
  {
    far: "M0 120 L60 80 L110 105 L170 55 L230 100 L290 70 L350 95 L400 75 L400 240 L0 240Z",
    mid: "M0 150 L50 125 L120 150 L190 110 L260 145 L330 120 L400 140 L400 240 L0 240Z",
  },
  {
    far: "M0 110 Q70 60 140 100 T280 85 T400 95 L400 240 L0 240Z",
    mid: "M0 150 Q80 115 160 145 T320 135 T400 140 L400 240 L0 240Z",
  },
  {
    far: "M0 115 L80 70 L130 95 L200 40 L260 90 L320 75 L400 105 L400 240 L0 240Z",
    mid: "M0 155 Q100 120 200 150 T400 135 L400 240 L0 240Z",
  },
] as const;

/** A stable small number from a string (FNV-1a), so the same destination keeps its cover. */
export function coverSeed(key: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function coverTone(key: string) {
  return COVER_TONES[coverSeed(key) % COVER_TONES.length] as (typeof COVER_TONES)[number];
}

/** The address of a photo the backend sent: its path on this API behind the API base URL. Without a
 * base URL (a build with none, a test) there is no address and the illustration stays. */
export function usePhotoUri(photo: Photo | null | undefined): string | null {
  const apiUrl = useContext(BackendContext)?.apiUrl ?? "";
  return photo && apiUrl ? `${apiUrl.replace(/\/$/, "")}${photo.url}` : null;
}

export function Cover({
  seedKey,
  photo,
  uri: givenUri,
  height,
  rounded = 0,
  children,
  scrim = false,
  creditInset = 0,
  style,
  testID,
}: {
  /** Usually the destination's identifier. */
  seedKey: string;
  /** The photo the backend sent for this trip or place, if any. */
  photo?: Photo | null;
  /** An address to show directly (tests, local files); `photo` is what screens pass. */
  uri?: string | null;
  height: number;
  rounded?: number;
  children?: ReactNode;
  /** A soft fade at the top and bottom, only for a cover that carries text or buttons (the trip's
   * header). It is a gradient, not a band: the middle of the photo stays clear. */
  scrim?: boolean;
  /** Lifts the photo credit's "i" clear of a sheet that curves over the cover's lower edge. */
  creditInset?: number;
  style?: ViewStyle;
  testID?: string;
}) {
  const photoUri = usePhotoUri(photo);
  const uri = givenUri ?? photoUri;
  const seed = coverSeed(seedKey);
  const tone = COVER_TONES[seed % COVER_TONES.length] as (typeof COVER_TONES)[number];
  const ridge = RIDGES[(seed >>> 4) % RIDGES.length] as (typeof RIDGES)[number];
  const sunX = 60 + ((seed >>> 8) % 280);
  const gradientId = `sky-${seed % 997}`;
  return (
    <View
      style={[
        styles.frame,
        { height, borderRadius: rounded },
        uri && photo && !givenUri ? { backgroundColor: photo.color } : null,
        style,
      ]}
      testID={testID}
      accessibilityIgnoresInvertColors
    >
      {uri ? (
        <>
          <Image
            source={{ uri }}
            style={StyleSheet.absoluteFill}
            resizeMode="cover"
            testID="cover-photo"
          />
        </>
      ) : (
        <Svg
          width="100%"
          height="100%"
          viewBox="0 0 400 240"
          preserveAspectRatio="xMidYMid slice"
          style={StyleSheet.absoluteFill}
          accessible={false}
          importantForAccessibility="no-hide-descendants"
          accessibilityElementsHidden
        >
          <Defs>
            <LinearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={tone.sky} />
              <Stop offset="1" stopColor={tone.haze} />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="400" height="240" fill={`url(#${gradientId})`} />
          <Circle cx={sunX} cy="52" r="18" fill={tone.haze} opacity={0.9} />
          <Path d={ridge.far} fill={tone.far} />
          <Path d={ridge.mid} fill={tone.mid} />
          <Path d="M0 170 Q100 158 200 166 T400 162 L400 240 L0 240Z" fill={tone.near} />
        </Svg>
      )}
      {scrim ? <Scrim /> : null}
      {children}
      {uri && photo && !givenUri ? <PhotoCredit photo={photo} inset={creditInset} /> : null}
    </View>
  );
}

function Scrim() {
  return (
    <Svg
      width="100%"
      height="100%"
      style={StyleSheet.absoluteFill}
      pointerEvents="none"
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
    >
      <Defs>
        <LinearGradient id="cover-scrim" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#0d1828" stopOpacity={0.5} />
          <Stop offset="0.28" stopColor="#0d1828" stopOpacity={0} />
          <Stop offset="0.5" stopColor="#0d1828" stopOpacity={0} />
          <Stop offset="1" stopColor="#0d1828" stopOpacity={0.62} />
        </LinearGradient>
      </Defs>
      <Rect x="0" y="0" width="100%" height="100%" fill="url(#cover-scrim)" />
    </Svg>
  );
}

const styles = StyleSheet.create({
  frame: { overflow: "hidden", backgroundColor: colors.surfaceMuted },
});

/**
 * The credit a photo's licence asks for (author, licence, Wikimedia Commons), kept out of the way:
 * a small "i" in the photo's bottom right corner. Pressing it shows the credit beside it, and the
 * credit opens the file's page. Every photo carries it; `Cover` draws it, so no screen can forget.
 */
export function PhotoCredit({
  photo,
  inset = 0,
}: {
  photo: Photo | null | undefined;
  inset?: number;
}) {
  const shown = usePhotoUri(photo);
  const [open, setOpen] = useState(false);
  if (!photo || !shown) return null;
  return (
    <View style={[creditStyles.corner, { bottom: spacing.sm + inset }]} pointerEvents="box-none">
      {open ? (
        <Pressable
          accessibilityRole="link"
          accessibilityLabel={`${photo.credit.text}. Opens the photo's page on Wikimedia Commons.`}
          onPress={() => void Linking.openURL(photo.credit.source_url)}
          style={creditStyles.bubble}
          testID="photo-credit"
        >
          <Text style={creditStyles.text} numberOfLines={3}>
            {photo.credit.text}
          </Text>
        </Pressable>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={open ? "Hide the photo credit" : "Show the photo credit"}
        accessibilityState={{ expanded: open }}
        hitSlop={12}
        onPress={() => setOpen((v) => !v)}
        style={creditStyles.button}
        testID="photo-credit-toggle"
      >
        <Icon name="info" size={14} color={colors.onImage} />
      </Pressable>
    </View>
  );
}

const creditStyles = StyleSheet.create({
  corner: {
    position: "absolute",
    right: spacing.sm,
    bottom: spacing.sm,
    left: spacing.sm,
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "flex-end",
    gap: spacing.xs,
  },
  button: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(20, 36, 58, 0.72)",
  },
  bubble: {
    flexShrink: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    backgroundColor: "rgba(20, 36, 58, 0.86)",
  },
  text: { ...typeScale.caption, color: colors.onImage, textDecorationLine: "underline" },
});
