import type { ExternalPlace, Stay, Trip } from "@detour/shared";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError } from "../api/unwrap";
import {
  Button,
  ChoiceRow,
  CompactHeader,
  ConfirmSheet,
  DropdownPanel,
  EmptyState,
  ErrorState,
  InlineStatus,
  KeyboardScrollView,
  ListRow,
  LoadingState,
  Notice,
  SearchField,
  Stepper,
  TextField,
} from "../components/ds";
import { keys } from "../data/actions";
import { useData, useResource } from "../data/DataProvider";
import { parseCoordinate } from "../domain/restaurants";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type, weight } from "../theme";

type StaysRoute = Extract<Route, { name: "stays" }>;
type Form = {
  id: string | null;
  name: string;
  lat: number | null;
  lon: number | null;
  first: number;
  last: number;
};

const MIN_QUERY = 2;

/** "Day 3" or "Days 1 to 3". */
export function dayRange(first: number, last: number): string {
  return first === last ? `Day ${first}` : `Days ${first} to ${last}`;
}

/**
 * Where the traveller sleeps (ADR 030): one or more stays, each for a range of days. Each day then
 * starts at its stay: Optimize and new proposals count the way from it to the first stop.
 */
export function StaysScreen({ route }: { route: StaysRoute }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const data = useData();
  const client = state.phase === "ready" ? state.connection.client : null;
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const stays = useResource<Stay[]>(keys.stays(route.tripId), (c) =>
    call(c.GET("/v1/trips/{trip_id}/stays", { params: { path: { trip_id: route.tripId } } })),
  );
  const trip = trips.data?.find((t) => t.id === route.tripId);
  const [form, setForm] = useState<Form | null>(null);
  const [removing, setRemoving] = useState<Stay | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<ExternalPlace[] | "none" | null>(null);
  const [searching, setSearching] = useState(false);
  const [byHand, setByHand] = useState({ lat: "", lon: "" });

  const q = query.trim();
  useEffect(() => {
    if (!form || form.id !== null || form.lat !== null || q.length < MIN_QUERY || !client || !trip)
      return;
    let current = true;
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const response = await call(
          client.GET("/v1/places/search", {
            params: {
              query: {
                q,
                lat: trip.destination.lat,
                lon: trip.destination.lon,
                limit: 8,
                include_external: true,
              },
            },
          }),
        );
        if (!current) return;
        const results = response.external.results ?? [];
        setFound(results.length ? results : "none");
      } catch (e) {
        if (current) setProblem(describeError(e));
      } finally {
        if (current) setSearching(false);
      }
    }, 350);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [form, q, client, trip]);

  if (stays.data === undefined || !trip) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Where you're staying" onBack={nav.back} />
        {stays.status === "error" ? (
          <ErrorState text={describeError(stays.error)} onRetry={stays.refresh} />
        ) : (
          <LoadingState text="Loading the stays…" />
        )}
      </View>
    );
  }

  const days = trip.duration_days;
  const covered = new Set(stays.data.flatMap((s) => range(s.first_day, s.last_day)));
  const nextFree = range(1, days).find((d) => !covered.has(d)) ?? null;
  const past = trip.status === "past";

  const open = (stay?: Stay) => {
    setProblem(null);
    setFound(null);
    setQuery("");
    setByHand({ lat: "", lon: "" });
    if (stay) {
      setForm({
        id: stay.id,
        name: stay.name,
        lat: stay.lat,
        lon: stay.lon,
        first: stay.first_day,
        last: stay.last_day,
      });
    } else {
      const first = nextFree ?? 1;
      let last = first;
      while (last < days && !covered.has(last + 1)) last += 1;
      setForm({ id: null, name: "", lat: null, lon: null, first, last });
    }
  };

  const changed = () => {
    data.invalidate(keys.stays(route.tripId));
    data.invalidate("itinerary:");
    stays.refresh();
  };

  const save = async () => {
    if (!form || !client || form.lat === null || form.lon === null || !form.name.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      const body = {
        name: form.name.trim(),
        lat: form.lat,
        lon: form.lon,
        first_day: form.first,
        last_day: form.last,
      };
      if (form.id === null) {
        await call(
          client.POST("/v1/trips/{trip_id}/stays", {
            params: { path: { trip_id: route.tripId } },
            body,
          }),
        );
      } else {
        await call(
          client.PATCH("/v1/trips/{trip_id}/stays/{stay_id}", {
            params: { path: { trip_id: route.tripId, stay_id: form.id } },
            body,
          }),
        );
      }
      setForm(null);
      changed();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!removing || !client) return;
    setBusy(true);
    try {
      await call(
        client.DELETE("/v1/trips/{trip_id}/stays/{stay_id}", {
          params: { path: { trip_id: route.tripId, stay_id: removing.id } },
        }),
      );
      setRemoving(null);
      setForm(null);
      changed();
    } catch (e) {
      setRemoving(null);
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const lat = parseCoordinate(byHand.lat, "lat");
  const lon = parseCoordinate(byHand.lon, "lon");
  const ready = form !== null && form.lat !== null && form.name.trim().length > 0;

  return (
    <KeyboardScrollView contentContainerStyle={styles.content}>
      <CompactHeader title="Where you're staying" subtitle={trip.title} onBack={nav.back} />
      <Text style={styles.lead}>
        Each day starts at its stay. Optimize and new proposals count the way from it to the first
        stop of the day; there is no trip back at night.
      </Text>

      {stays.data.length === 0 && form === null ? (
        <EmptyState
          title="No stay yet"
          text="Add a hotel, an apartment or any address, for some days or all of them."
        />
      ) : (
        <View>
          {stays.data.map((s) => (
            <ListRow
              key={s.id}
              icon="home"
              title={s.name}
              detail={dayRange(s.first_day, s.last_day)}
              testID={`stay-${s.id}`}
              disabled={past}
              disabledLabel="Past trip"
              onPress={() => open(s)}
            />
          ))}
        </View>
      )}

      {problem ? (
        <View style={styles.pad}>
          <Notice tone="error">{problem}</Notice>
        </View>
      ) : null}

      {form === null ? (
        <View style={styles.pad}>
          {!past ? (
            <Button
              label="Add a stay"
              testID="stay-add"
              fill
              disabled={nextFree === null || !client}
              onPress={() => open()}
            />
          ) : null}
          {nextFree === null && !past ? (
            <Text style={styles.small}>Every day of the trip has a stay.</Text>
          ) : null}
        </View>
      ) : (
        <View style={styles.pad}>
          {form.id === null && form.lat === null ? (
            <>
              <SearchField
                label="Hotel, apartment or address"
                value={query}
                onChangeText={(t) => {
                  setQuery(t);
                  setFound(null);
                }}
                onClear={() => {
                  setQuery("");
                  setFound(null);
                }}
                hint="At least two letters. Searched on OpenStreetMap through the Detour server."
                testID="stay-search"
              />
              {searching ? <InlineStatus text="Searching…" busy /> : null}
              {found === "none" ? (
                <Text style={styles.small}>Nothing found. Try the address, or enter it below.</Text>
              ) : null}
              {Array.isArray(found) ? (
                <DropdownPanel>
                  {found.map((p, n) => (
                    <ChoiceRow
                      key={`${p.ref ?? n}`}
                      icon="home"
                      title={p.name}
                      meta={[p.street, p.city, p.country].filter(Boolean).join(" · ")}
                      selected={false}
                      onPress={() => setForm({ ...form, name: p.name, lat: p.lat, lon: p.lon })}
                    />
                  ))}
                </DropdownPanel>
              ) : null}
              <Text style={styles.label}>Or enter it by hand</Text>
              <TextField
                label="Name"
                value={form.name}
                onChangeText={(t) => setForm({ ...form, name: t })}
              />
              <TextField
                label="Latitude"
                value={byHand.lat}
                onChangeText={(t) => setByHand({ ...byHand, lat: t })}
                keyboardType="numbers-and-punctuation"
              />
              <TextField
                label="Longitude"
                value={byHand.lon}
                onChangeText={(t) => setByHand({ ...byHand, lon: t })}
                keyboardType="numbers-and-punctuation"
              />
              <Button
                label="Use these coordinates"
                variant="secondary"
                disabled={lat === null || lon === null || !form.name.trim()}
                onPress={() => setForm({ ...form, lat, lon })}
              />
            </>
          ) : (
            <TextField
              label="Name"
              value={form.name}
              onChangeText={(t) => setForm({ ...form, name: t })}
            />
          )}

          <Text style={styles.label}>Which days</Text>
          <View style={styles.steppers}>
            <View style={styles.stepper}>
              <Text style={styles.small}>From</Text>
              <Stepper
                value={form.first}
                min={1}
                max={days}
                onChange={(v) => setForm({ ...form, first: v, last: Math.max(form.last, v) })}
                format={(v) => `Day ${v}`}
                accessibilityLabel="First day"
                decreaseLabel="Earlier first day"
                increaseLabel="Later first day"
                testID="stay-first"
              />
            </View>
            <View style={styles.stepper}>
              <Text style={styles.small}>To</Text>
              <Stepper
                value={form.last}
                min={form.first}
                max={days}
                onChange={(v) => setForm({ ...form, last: v })}
                format={(v) => `Day ${v}`}
                accessibilityLabel="Last day"
                decreaseLabel="Earlier last day"
                increaseLabel="Later last day"
                testID="stay-last"
              />
            </View>
          </View>

          <Button
            label={form.id === null ? "Save the stay" : "Save changes"}
            testID="stay-save"
            fill
            loading={busy}
            disabled={busy || !ready}
            onPress={() => void save()}
          />
          <Button label="Cancel" variant="secondary" fill onPress={() => setForm(null)} />
          {form.id !== null ? (
            <Button
              label="Remove this stay"
              variant="ghost"
              tone="danger"
              onPress={() => setRemoving(stays.data?.find((s) => s.id === form.id) ?? null)}
            />
          ) : null}
        </View>
      )}

      <ConfirmSheet
        visible={removing !== null}
        title="Remove this stay?"
        message={`${removing?.name ?? "It"} will no longer be where ${removing ? dayRange(removing.first_day, removing.last_day).toLowerCase() : "those days"} start. Your plan keeps its stops.`}
        confirmLabel="Yes, remove it"
        cancelLabel="Keep it"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
    </KeyboardScrollView>
  );
}

function range(first: number, last: number): number[] {
  return Array.from({ length: last - first + 1 }, (_, i) => first + i);
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl, gap: layout.block },
  pad: { paddingHorizontal: layout.gutter, gap: spacing.sm },
  lead: { ...type.label, color: colors.muted, paddingHorizontal: layout.gutter },
  label: { ...type.label, fontWeight: weight.semibold, color: colors.text },
  small: { ...type.caption, color: colors.muted },
  steppers: { flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" },
  stepper: { gap: spacing.xs },
});
