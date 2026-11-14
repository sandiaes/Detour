import type { DestinationResult } from "@detour/shared";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError } from "../api/unwrap";
import { colors, radius, spacing, type } from "../theme";
import { pluralise } from "../util/format";
import { Button } from "./Button";
import { Icon } from "./ds/Icon";
import { IconButton, Sheet } from "./ds/primitives";

/** One city of a multi-city trip being edited (ADR 024). */
export type StopDraft = { cityId: number; name: string; detail: string; days: number };

export const MIN_STOPS = 2;
export const MAX_STOPS = 6;
export const MAX_TRIP_DAYS = 30;

/** Days shared evenly between the stops, the remainder to the first ones (ADR 024, decision 5). */
export function evenSplit(total: number, count: number): number[] {
  if (count <= 0) return [];
  const days = Math.max(total, count);
  const base = Math.floor(days / count);
  const extra = days % count;
  return Array.from({ length: count }, (_, i) => base + (i < extra ? 1 : 0));
}

/** Why the stops cannot be saved, in words, or null. The server checks the same rules. */
export function stopsProblem(stops: StopDraft[]): string | null {
  if (stops.length < MIN_STOPS) return "A multi-city trip has at least two cities.";
  if (stops.length > MAX_STOPS) return `A trip has at most ${MAX_STOPS} cities.`;
  for (let i = 1; i < stops.length; i++) {
    if (stops[i]?.cityId === stops[i - 1]?.cityId) {
      return `Cities ${i} and ${i + 1} are the same: give that city more days instead.`;
    }
  }
  const total = stops.reduce((n, s) => n + s.days, 0);
  if (total > MAX_TRIP_DAYS) return `A trip has at most ${MAX_TRIP_DAYS} days.`;
  return null;
}

export function moveStop(stops: StopDraft[], from: number, to: number): StopDraft[] {
  if (to < 0 || to >= stops.length) return stops;
  const next = [...stops];
  const [moved] = next.splice(from, 1);
  if (moved) next.splice(to, 0, moved);
  return next;
}

/**
 * The cities of a multi-city trip as hairline rows: the city, its days (minus and plus), Up and
 * Down to reorder, and Remove; "Add another city" opens a search of cities (ADR 024, decision 24).
 * The order is the user's; nothing here reorders.
 */
export function StopList({
  stops,
  onChange,
  canAdd = true,
}: {
  stops: StopDraft[];
  onChange: (stops: StopDraft[]) => void;
  canAdd?: boolean;
}) {
  const [searching, setSearching] = useState(false);
  const total = stops.reduce((n, s) => n + s.days, 0);
  const setDays = (i: number, days: number) =>
    onChange(stops.map((s, n) => (n === i ? { ...s, days } : s)));
  return (
    <View style={s.list} testID="stop-list">
      {stops.map((stop, i) => (
        <View key={`${stop.cityId}-${i}`} style={s.row} testID={`stop-${i}`}>
          <View style={s.number}>
            <Text style={s.numberText}>{i + 1}</Text>
          </View>
          <View style={s.body}>
            <Text style={s.name} numberOfLines={1}>
              {stop.name}
            </Text>
            {stop.detail ? (
              <Text style={s.detail} numberOfLines={1}>
                {stop.detail}
              </Text>
            ) : null}
            <View style={s.days}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Fewer days in ${stop.name}`}
                accessibilityState={{ disabled: stop.days <= 1 }}
                disabled={stop.days <= 1}
                hitSlop={8}
                onPress={() => setDays(i, stop.days - 1)}
                style={s.step}
                testID={`stop-${i}-fewer`}
              >
                <Text style={[s.stepText, stop.days <= 1 && s.stepOff]}>−</Text>
              </Pressable>
              <Text
                style={s.daysText}
                accessibilityLabel={`${stop.name}: ${pluralise(stop.days, "day")}`}
              >
                {pluralise(stop.days, "day")}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`More days in ${stop.name}`}
                accessibilityState={{ disabled: total >= MAX_TRIP_DAYS }}
                disabled={total >= MAX_TRIP_DAYS}
                hitSlop={8}
                onPress={() => setDays(i, stop.days + 1)}
                style={s.step}
                testID={`stop-${i}-more`}
              >
                <Text style={[s.stepText, total >= MAX_TRIP_DAYS && s.stepOff]}>+</Text>
              </Pressable>
            </View>
          </View>
          <View style={s.actions}>
            {i > 0 ? (
              <IconButton
                icon="up"
                label={`Move ${stop.name} earlier`}
                compact
                onPress={() => onChange(moveStop(stops, i, i - 1))}
                testID={`stop-${i}-up`}
              />
            ) : null}
            {i < stops.length - 1 ? (
              <IconButton
                icon="down"
                label={`Move ${stop.name} later`}
                compact
                onPress={() => onChange(moveStop(stops, i, i + 1))}
                testID={`stop-${i}-down`}
              />
            ) : null}
            <IconButton
              icon="close"
              label={`Remove ${stop.name}`}
              compact
              onPress={() => onChange(stops.filter((_, n) => n !== i))}
              testID={`stop-${i}-remove`}
            />
          </View>
        </View>
      ))}
      <Text style={s.total} testID="stop-total">
        {pluralise(stops.length, "city", "cities")} · {pluralise(total, "day")} in all
      </Text>
      {canAdd && stops.length < MAX_STOPS ? (
        <Button
          label="Add another city"
          icon="add"
          variant="secondary"
          size="compact"
          onPress={() => setSearching(true)}
          testID="add-city"
        />
      ) : null}
      {searching ? (
        <CitySearchSheet
          onClose={() => setSearching(false)}
          onChoose={(r) => {
            setSearching(false);
            onChange([
              ...stops,
              {
                cityId: Number(r.ref),
                name: r.name,
                detail: [r.admin1_name, r.country_name].filter(Boolean).join(", "),
                days: 1,
              },
            ]);
          }}
        />
      ) : null}
    </View>
  );
}

/** A search of cities to add as a stop: only cities in an imported region can be chosen. */
export function CitySearchSheet({
  onChoose,
  onClose,
}: {
  onChoose: (r: DestinationResult) => void;
  onClose: () => void;
}) {
  const { state } = useBackend();
  const client = state.phase === "ready" ? state.connection.client : null;
  const [query, setQuery] = useState("");
  const [answers, setAnswers] = useState<Record<string, DestinationResult[] | string>>({});
  const q = query.trim();
  const key = q.toLowerCase();
  const needed = q.length >= 2 && answers[key] === undefined && client !== null;
  useEffect(() => {
    if (!needed || !client) return;
    let live = true;
    const timer = setTimeout(() => {
      call(client.GET("/v1/destinations/search", { params: { query: { q, limit: 8 } } }))
        .then((r) => live && setAnswers((a) => ({ ...a, [key]: r.results })))
        .catch((e: unknown) => live && setAnswers((a) => ({ ...a, [key]: describeError(e) })));
    }, 350);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [needed, client, q, key]);
  const answer = answers[key];
  return (
    <Sheet visible title="Add a city" onClose={onClose}>
      <View style={s.searchRow}>
        <Icon name="search" size={18} color={colors.muted} />
        <TextInput
          accessibilityLabel="City"
          placeholder="City, for example Salzburg"
          placeholderTextColor={colors.muted}
          value={query}
          onChangeText={setQuery}
          autoFocus
          autoCorrect={false}
          style={s.searchInput}
          testID="city-search-input"
        />
      </View>
      {typeof answer === "string" ? (
        <Text style={s.detail}>{answer}</Text>
      ) : answer === undefined ? (
        q.length >= 2 ? (
          <Text style={s.detail}>Searching…</Text>
        ) : null
      ) : answer.filter((r) => r.kind === "city").length === 0 ? (
        <Text style={s.detail}>No city matches “{q}” in the imported regions.</Text>
      ) : (
        answer
          .filter((r) => r.kind === "city")
          .map((r) => {
            const ok = r.planning_available && !r.unavailable_reason;
            return (
              <Pressable
                key={r.ref}
                accessibilityRole="button"
                accessibilityState={{ disabled: !ok }}
                disabled={!ok}
                onPress={() => onChoose(r)}
                style={[s.result, !ok && s.resultOff]}
                testID={`city-result-${r.ref}`}
              >
                <Text style={s.name}>{r.name}</Text>
                <Text style={s.detail}>
                  {[r.admin1_name, r.country_name].filter(Boolean).join(", ")}
                  {ok ? "" : " · Not available yet: this region's data has not been imported."}
                </Text>
              </Pressable>
            );
          })
      )}
    </Sheet>
  );
}

const RULE = StyleSheet.hairlineWidth;

const s = StyleSheet.create({
  list: { gap: spacing.sm },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: RULE,
    borderBottomColor: colors.border,
  },
  number: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  numberText: { ...type.caption, color: colors.onPrimary, fontWeight: "700" },
  body: { flex: 1, gap: 2 },
  name: { ...type.small, color: colors.text, fontWeight: "600" },
  detail: { ...type.caption, color: colors.muted },
  days: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: 2 },
  step: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.outline,
    alignItems: "center",
    justifyContent: "center",
  },
  stepText: { ...type.body, color: colors.text },
  stepOff: { color: colors.border },
  daysText: { ...type.caption, color: colors.text, minWidth: 48, textAlign: "center" },
  actions: { flexDirection: "row", alignItems: "center" },
  total: { ...type.caption, color: colors.muted },
  searchRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    borderBottomWidth: RULE,
    borderBottomColor: colors.outline,
    minHeight: 48,
  },
  searchInput: { flex: 1, ...type.body, color: colors.text },
  result: {
    minHeight: 48,
    paddingVertical: spacing.sm,
    borderBottomWidth: RULE,
    borderBottomColor: colors.border,
    gap: 2,
  },
  resultOff: { opacity: 0.6 },
});
