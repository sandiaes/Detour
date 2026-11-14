import type { CoverCandidate } from "@detour/shared";
import { useContext, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { BackendContext } from "../../api/BackendProvider";
import { describeError } from "../../api/unwrap";
import { colors, radius, spacing, type } from "../../theme";
import { Button } from "../Button";
import { LoadingState, Notice } from "../ui";
import { FittedPhoto } from "./Cover";
import { Icon } from "./Icon";
import { Sheet } from "./primitives";

/** One destination whose photos can be chosen (a city or area; each stop of a multi-city trip). */
export type CoverSource = { kind: "city" | "area"; ref: string; name: string };

/**
 * "Change photo" (ADR 022, decision 15; amendment, decisions g and h): up to 12 freely licensed
 * photos of the destination, three across, each with its credit. The previews come from the
 * backend; the app never asks Wikimedia. The first request for a destination can take a while (the
 * backend fetches and resizes the previews), so the sheet says so. "Automatic photo" goes back to
 * the photo found for the destination.
 */
export function CoverPicker({
  visible,
  sources,
  load,
  onChoose,
  onClose,
  chosen,
}: {
  visible: boolean;
  sources: CoverSource[];
  load: (kind: "city" | "area", ref: string) => Promise<CoverCandidate[]>;
  /** null: the automatic photo. */
  onChoose: (candidate: CoverCandidate | null) => Promise<void> | void;
  onClose: () => void;
  /** The file chosen now, if any (marked as selected). */
  chosen?: string | null;
}) {
  const apiUrl = (useContext(BackendContext)?.apiUrl ?? "").replace(/\/$/, "");
  const [sourceIndex, setSourceIndex] = useState(0);
  // Answers by destination; none yet means loading. Set only when an answer arrives.
  const [answers, setAnswers] = useState<
    Record<
      string,
      { status: "ready"; items: CoverCandidate[] } | { status: "error"; message: string }
    >
  >({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const source = sources[Math.min(sourceIndex, sources.length - 1)];

  const sourceKey = source ? `${source.kind}:${source.ref}` : "";
  const state = answers[sourceKey] ?? { status: "loading" as const };
  const needed = visible && source !== undefined && answers[sourceKey] === undefined;

  useEffect(() => {
    if (!needed || !source) return;
    let live = true;
    load(source.kind, source.ref)
      .then((items) => {
        if (live) setAnswers((a) => ({ ...a, [sourceKey]: { status: "ready", items } }));
      })
      .catch((e: unknown) => {
        if (live)
          setAnswers((a) => ({
            ...a,
            [sourceKey]: { status: "error", message: describeError(e) },
          }));
      });
    return () => {
      live = false;
    };
  }, [needed, source, sourceKey, load]);

  const choose = async (candidate: CoverCandidate | null) => {
    setSaving(candidate?.commons_file ?? "automatic");
    setError(null);
    try {
      await onChoose(candidate);
      onClose();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setSaving(null);
    }
  };

  return (
    <Sheet visible={visible} title="Change photo" onClose={onClose}>
      {sources.length > 1 ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.tabs}
        >
          {sources.map((src, i) => (
            <Pressable
              key={`${src.kind}:${src.ref}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: i === sourceIndex }}
              hitSlop={6}
              onPress={() => setSourceIndex(i)}
              style={[s.tab, i === sourceIndex && s.tabOn]}
              testID={`cover-source-${i}`}
            >
              <Text style={[s.tabText, i === sourceIndex && s.tabTextOn]}>{src.name}</Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {state.status === "loading" ? (
        <LoadingState text="Finding photos. The first time for a place can take half a minute." />
      ) : state.status === "error" ? (
        <Notice tone="error">{state.message}</Notice>
      ) : state.items.length === 0 ? (
        <Text style={s.note}>
          No freely licensed photo of {source?.name ?? "this place"} passes Detour&apos;s checks.
          The illustration stays.
        </Text>
      ) : (
        <ScrollView style={s.scroll} contentContainerStyle={s.grid}>
          {state.items.map((c) => {
            const on = chosen === c.commons_file;
            return (
              <Pressable
                key={c.commons_file}
                accessibilityRole="button"
                accessibilityLabel={`Photo by ${c.credit.author}, ${c.credit.licence}`}
                accessibilityState={{ selected: on, busy: saving === c.commons_file }}
                disabled={saving !== null}
                onPress={() => void choose(c)}
                style={[s.cell, on && s.cellOn]}
                testID={`cover-candidate-${c.commons_file}`}
              >
                <View style={s.frame}>
                  {apiUrl ? <FittedPhoto uri={`${apiUrl}${c.preview_url}`} photoSize={c} /> : null}
                  {on ? (
                    <View style={s.tick}>
                      <Icon name="check" size={14} color={colors.onPrimary} />
                    </View>
                  ) : null}
                </View>
                <Text style={s.credit} numberOfLines={2}>
                  {c.credit.author} · {c.credit.licence}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
      <Button
        label="Automatic photo"
        variant="secondary"
        size="compact"
        icon="refresh"
        loading={saving === "automatic"}
        disabled={saving !== null}
        hint="Use the photo Detour finds for the destination"
        onPress={() => void choose(null)}
        testID="cover-automatic"
      />
      <Text style={s.note}>
        Photos from Wikimedia Commons, shown with their author and licence.
      </Text>
    </Sheet>
  );
}

const s = StyleSheet.create({
  tabs: { gap: spacing.sm, paddingBottom: spacing.sm },
  tab: {
    minHeight: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.outline,
    justifyContent: "center",
  },
  tabOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  tabText: { ...type.caption, color: colors.text },
  tabTextOn: { color: colors.onPrimary },
  scroll: { maxHeight: 420 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  cell: { width: "31%", gap: spacing.xs, borderRadius: radius.sm },
  cellOn: { opacity: 1 },
  frame: {
    aspectRatio: 4 / 3,
    borderRadius: radius.sm,
    overflow: "hidden",
    backgroundColor: colors.surfaceMuted,
  },
  tick: {
    position: "absolute",
    top: spacing.xs,
    right: spacing.xs,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  credit: { ...type.caption, color: colors.muted },
  note: { ...type.caption, color: colors.muted },
});
