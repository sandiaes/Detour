import type { DestinationResult } from "@detour/shared";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError } from "../api/unwrap";
import { border, colors, spacing, type, weight } from "../theme";
import { pluralise } from "../util/format";
import {
  Button,
  ChoiceRow,
  DropdownPanel,
  IconButton,
  InlineStatus,
  SearchField,
  Sheet,
  Stepper,
  StopMark,
} from "./ds";

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
          <StopMark kind="city" label={i + 1} />
          <View style={s.body}>
            <Text style={s.name} numberOfLines={1}>
              {stop.name}
            </Text>
            {stop.detail ? (
              <Text style={s.detail} numberOfLines={1}>
                {stop.detail}
              </Text>
            ) : null}
            <Stepper
              value={stop.days}
              min={1}
              max={stop.days + Math.max(0, MAX_TRIP_DAYS - total)}
              onChange={(d) => setDays(i, d)}
              format={(d) => pluralise(d, "day")}
              accessibilityLabel={`${stop.name}: ${pluralise(stop.days, "day")}`}
              decreaseLabel={`Fewer days in ${stop.name}`}
              increaseLabel={`More days in ${stop.name}`}
              testID={`stop-${i}`}
            />
          </View>
          <View style={s.actions}>
            {i > 0 ? (
              <IconButton
                icon="up"
                label={`Move ${stop.name} earlier`}
                size="sm"
                onPress={() => onChange(moveStop(stops, i, i - 1))}
                testID={`stop-${i}-up`}
              />
            ) : null}
            {i < stops.length - 1 ? (
              <IconButton
                icon="down"
                label={`Move ${stop.name} later`}
                size="sm"
                onPress={() => onChange(moveStop(stops, i, i + 1))}
                testID={`stop-${i}-down`}
              />
            ) : null}
            <IconButton
              icon="close"
              label={`Remove ${stop.name}`}
              size="sm"
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
          size="sm"
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
      <SearchField
        label="City"
        accessibilityLabel="City"
        placeholder="City, for example Salzburg"
        value={query}
        onChangeText={setQuery}
        onClear={() => setQuery("")}
        autoFocus
        testID="city-search-input"
      />
      {typeof answer === "string" ? (
        <InlineStatus text={answer} />
      ) : answer === undefined ? (
        q.length >= 2 ? (
          <InlineStatus text="Searching…" busy />
        ) : null
      ) : answer.filter((r) => r.kind === "city").length === 0 ? (
        <InlineStatus text={`No city matches “${q}” in the imported regions.`} />
      ) : (
        <DropdownPanel>
          {answer
            .filter((r) => r.kind === "city")
            .map((r) => {
              const ok = r.planning_available && !r.unavailable_reason;
              return (
                <ChoiceRow
                  key={r.ref}
                  icon="city"
                  title={r.name}
                  meta={[r.admin1_name, r.country_name].filter(Boolean).join(", ")}
                  selected={false}
                  disabled={!ok}
                  disabledLabel="Not imported"
                  accessibilityLabel={`${r.name}, ${[r.admin1_name, r.country_name].filter(Boolean).join(", ")}${ok ? "" : ". Not available yet: this region's data has not been imported."}`}
                  onPress={() => onChoose(r)}
                  testID={`city-result-${r.ref}`}
                />
              );
            })}
        </DropdownPanel>
      )}
    </Sheet>
  );
}

const s = StyleSheet.create({
  list: { gap: spacing.sm },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  body: { flex: 1, gap: spacing.xxs },
  name: { ...type.label, color: colors.text, fontWeight: weight.semibold },
  detail: { ...type.caption, color: colors.muted },
  actions: { flexDirection: "row", alignItems: "center" },
  total: { ...type.caption, color: colors.muted },
});
