import type { Photo } from "@detour/shared";
import { type ReactNode, useContext } from "react";
import { Image, Linking, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from "react-native-svg";

import { BackendContext } from "../../api/BackendProvider";
import { colors, type as typeScale } from "../../theme";

// A destination's or place's cover (ADR 021, ADR 022). A photo appears only when the backend sent
// one (`photo`: Wikimedia Commons, served through the backend); otherwise nothing is invented and
// the cover is a calm illustrated landscape whose colours and hills are chosen from the
// destination identifier, so a trip always looks the same. A photo has a scrim under the text and
// the photo's average colour behind it while it loads. A photo is never shown without its credit
// somewhere on the same screen (`PhotoCredit`).

/** The `mid` and `near` colours are the hills under the text: white on both is checked at 4.5:1
 * (theme.test.ts), and a dark gradient over the lower part adds a margin. */
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
          <View style={styles.scrim} />
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
            <LinearGradient id={`${gradientId}-scrim`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0.35" stopColor="#0e1824" stopOpacity={0} />
              <Stop offset="1" stopColor="#0e1824" stopOpacity={0.55} />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="400" height="240" fill={`url(#${gradientId})`} />
          <Circle cx={sunX} cy="52" r="18" fill={tone.haze} opacity={0.9} />
          <Path d={ridge.far} fill={tone.far} />
          <Path d={ridge.mid} fill={tone.mid} />
          <Path d="M0 170 Q100 158 200 166 T400 162 L400 240 L0 240Z" fill={tone.near} />
          <Rect x="0" y="0" width="400" height="240" fill={`url(#${gradientId}-scrim)`} />
        </Svg>
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { overflow: "hidden", backgroundColor: colors.surfaceMuted },
  scrim: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    height: "55%",
    backgroundColor: colors.scrim,
  },
});

/**
 * The credit a photo's licence asks for: author, licence and Wikimedia Commons, opening the file's
 * page. Shown on the screen that shows the photo (the trip overview, the place), not on a list card.
 */
export function PhotoCredit({ photo }: { photo: Photo | null | undefined }) {
  const shown = usePhotoUri(photo);
  if (!photo || !shown) return null;
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={`${photo.credit.text}. Opens the photo's page on Wikimedia Commons.`}
      onPress={() => void Linking.openURL(photo.credit.source_url)}
      style={creditStyles.target}
      testID="photo-credit"
    >
      <Text style={creditStyles.text}>{photo.credit.text}</Text>
    </Pressable>
  );
}

const creditStyles = StyleSheet.create({
  target: { minHeight: 48, justifyContent: "center", alignSelf: "flex-start" },
  text: {
    ...typeScale.caption,
    color: colors.muted,
    textDecorationLine: "underline",
  },
});
