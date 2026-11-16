import type {
  ApiClient,
  Day,
  Item,
  ItemCreate,
  ItemUpdate,
  Itinerary,
  Stay,
  Trip,
} from "@detour/shared";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, callEmpty, describeError } from "../api/unwrap";
import {
  Button,
  Chip,
  ChoiceRow,
  CompactHeader,
  ConfirmSheet,
  EmptyState,
  ErrorState,
  KeyboardScrollView,
  LoadingState,
  Notice,
  SegmentedControl,
  SelectField,
  TextField,
  TimeField,
} from "../components/ds";
import { DurationField } from "../components/ds/DurationField";
import { keys } from "../data/actions";
import { useData, useResource } from "../data/DataProvider";
import { parseClock } from "../domain/clock";
import { minutesOf } from "../domain/itinerary";
import { PAST_TRIP_NOTE, isReadOnly } from "../domain/trips";
import {
  MODE_ICON,
  MODE_LABEL,
  NOT_ENTERED,
  TRANSPORT_MODES,
  type TransportMode,
  isLeg,
  legClash,
  legPosition,
} from "../domain/transport";
import { type Route, useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type, weight } from "../theme";
import { formatMinutes } from "../util/format";

type LegRoute = Extract<Route, { name: "transportLeg" }>;

/** One end of a leg: a name, and a point when it was picked from the trip. */
export type End = { name: string; lat: number | null; lon: number | null };

type Option = End & { key: string; group: string };

const NOTE_MAX = 500;
const NAME_MAX = 120;

/** What the From and To lists offer, in this order: the trip's cities (its destination when it has
 * one city), its stays, then the day's stops, each once by name. */
export function endOptions(trip: Trip, day: Day | undefined, stays: Stay[]): Option[] {
  const out: Option[] = [];
  const seen = new Set<string>();
  const add = (group: string, name: string, lat: number | null, lon: number | null) => {
    const key = `${group}:${name.toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ key, group, name, lat, lon });
  };
  // Cities first, then stays, then the day's stops (owner, 2026-11-16); "Type a name" comes last.
  for (const s of trip.stops ?? []) add("Cities of the trip", s.name, s.lat, s.lon);
  if (!trip.stops?.length) {
    add("Cities of the trip", trip.destination.name, trip.destination.lat, trip.destination.lon);
  }
  for (const s of stays) add("Where you're staying", s.name, s.lat, s.lon);
  for (const item of day?.items ?? []) {
    if (item.type === "transport" || item.lat === null || item.lon === null) continue;
    add("Stops of this day", item.display_name, item.lat, item.lon);
  }
  return out;
}

/** The leg being changed, with its day; null when adding one or when it is gone. */
function findLeg(days: Day[] | undefined, itemId: string | undefined) {
  if (!itemId) return null;
  for (const d of days ?? []) {
    const found = d.items.find((i) => i.id === itemId);
    if (found) return { day: d, item: found };
  }
  return null;
}

/** Minutes from a start and an arrival time; an arrival earlier than the start is the next day. */
export function lengthFromArrival(start: string, arrival: string): number | null {
  const a = minutesOf(start);
  const b = minutesOf(arrival);
  if (a === null || b === null || a === b) return null;
  return b > a ? b - a : 24 * 60 - a + b;
}

/**
 * Add or change a transport leg (ADR 032): how the user travelled, entered by hand. Nothing here
 * is computed or looked up; a length not entered stays unknown. No price, operator or booking.
 */
export function TransportLegScreen({ route }: { route: LegRoute }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const data = useData();
  const client = state.phase === "ready" ? state.connection.client : null;
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === route.tripId);
  const itinerary = useResource<Itinerary>(keys.itinerary(route.itineraryId), (c) =>
    call(
      c.GET("/v1/itineraries/{itinerary_id}", {
        params: { path: { itinerary_id: route.itineraryId } },
      }),
    ),
  );
  const stays = useResource<Stay[]>(keys.stays(route.tripId), (c) =>
    call(c.GET("/v1/trips/{trip_id}/stays", { params: { path: { trip_id: route.tripId } } })),
  );
  const existing = findLeg(itinerary.data?.days, route.itemId);

  if (!trip || !itinerary.data) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Transport" onBack={nav.back} />
        {itinerary.error || trips.error ? (
          <ErrorState
            text={describeError(itinerary.error ?? trips.error)}
            onRetry={itinerary.refresh}
          />
        ) : (
          <LoadingState text="Loading the plan…" />
        )}
      </View>
    );
  }
  if (route.itemId && (!existing || !isLeg(existing.item))) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Transport" onBack={nav.back} />
        <ErrorState text="This transport leg is no longer in the plan." />
      </View>
    );
  }
  if (isReadOnly(trip)) {
    // A past trip is read-only (ADR 006, amendment of 2026-11-17): the leg is shown, not edited.
    const leg = existing?.item;
    return (
      <View style={styles.fill}>
        <CompactHeader title="Transport" subtitle={trip.title} onBack={nav.back} />
        <EmptyState
          title={leg?.display_name ?? "Transport"}
          text={PAST_TRIP_NOTE}
          action={{ label: "Back", onPress: nav.back }}
        />
      </View>
    );
  }
  return (
    <LegForm
      key={route.itemId ?? "new"}
      route={route}
      trip={trip}
      days={itinerary.data.days}
      stays={stays.data ?? []}
      existing={existing}
      onDone={() => {
        data.invalidate(keys.itinerary(route.itineraryId));
        data.invalidate(keys.itineraries(route.tripId));
        nav.back();
      }}
      client={client}
    />
  );
}

function LegForm({
  route,
  trip,
  days,
  stays,
  existing,
  onDone,
  client,
}: {
  route: LegRoute;
  trip: Trip;
  days: Day[];
  stays: Stay[];
  existing: { day: Day; item: Item } | null;
  onDone: () => void;
  client: ApiClient | null;
}) {
  const nav = useNavigation();
  const leg = existing && isLeg(existing.item) ? existing.item : null;
  const sorted = [...days].sort((a, b) => a.day_index - b.day_index);
  const firstDay = existing?.day.day_index ?? route.day ?? sorted[0]?.day_index ?? 1;
  const [mode, setMode] = useState<TransportMode>(leg?.transport.mode ?? "train");
  const [dayIndex, setDayIndex] = useState(firstDay);
  const day = sorted.find((d) => d.day_index === dayIndex);
  const options = endOptions(trip, day, stays);
  const [from, setFrom] = useState<End | null>(
    leg
      ? {
          name: leg.transport.from_name,
          lat: leg.transport.from_lat ?? null,
          lon: leg.transport.from_lon ?? null,
        }
      : null,
  );
  const [to, setTo] = useState<End | null>(
    leg
      ? {
          name: leg.transport.to_name,
          lat: leg.transport.to_lat ?? null,
          lon: leg.transport.to_lon ?? null,
        }
      : null,
  );
  const [open, setOpen] = useState<"mode" | "day" | "from" | "to" | null>(null);
  const [typing, setTyping] = useState<"from" | "to" | null>(null);
  const [typed, setTyped] = useState("");
  const [start, setStart] = useState(leg?.start_time?.slice(0, 5) ?? "");
  const [lengthBy, setLengthBy] = useState<"length" | "arrival">("length");
  const [minutes, setMinutes] = useState<number | null>(leg?.duration_minutes ?? null);
  const [lengthValid, setLengthValid] = useState(true);
  const [arrival, setArrival] = useState("");
  const multiCity = (trip.stops?.length ?? 0) > 1;
  const [journey, setJourney] = useState(leg?.transport.is_journey ?? false);
  const [note, setNote] = useState(leg?.transport.note ?? "");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);

  const startClock = parseClock(start);
  const startOk = start.trim() === "" || startClock !== null;
  const fromArrival =
    lengthBy === "arrival" && startClock && parseClock(arrival)
      ? lengthFromArrival(startClock, parseClock(arrival) as string)
      : null;
  const length = lengthBy === "arrival" ? fromArrival : minutes;
  const arrivalProblem =
    lengthBy === "arrival" && arrival.trim() !== ""
      ? !startClock
        ? "set the start time first"
        : parseClock(arrival) === null
          ? "use hours and minutes, like 11:42"
          : fromArrival === null
            ? "the arrival is the same as the start"
            : null
      : null;
  const ready =
    from !== null &&
    to !== null &&
    startOk &&
    (lengthBy === "length" ? lengthValid : arrivalProblem === null) &&
    !busy &&
    client !== null;

  const choose = (which: "from" | "to", end: End) => {
    if (which === "from") setFrom(end);
    else setTo(end);
    setOpen(null);
  };

  // Where the leg goes (after its From stop, else first for a journey, else by time, else last)
  // and what its times run into (owner, 2026-11-16). A changed leg is placed again only when its
  // day, From, start or journey mark changed, so a leg the user left alone stays where it is.
  const moved =
    !leg ||
    !existing ||
    dayIndex !== existing.day.day_index ||
    from?.name !== leg.transport.from_name ||
    (from?.lat ?? null) !== (leg.transport.from_lat ?? null) ||
    (startClock ?? null) !== (leg.start_time?.slice(0, 5) ?? null) ||
    journey !== leg.transport.is_journey;
  const position =
    moved || !leg || !existing
      ? legPosition(day, { from, start: startClock, journey }, leg?.id)
      : existing.day.items.findIndex((i) => i.id === leg.id) + 1;
  const clash = legClash(day, position, { start: startClock, minutes: length }, leg?.id);
  const [shifting, setShifting] = useState(false);

  const attempt = () => {
    setProblem(null);
    if (clash.kind === "earlier") {
      setProblem(
        `It leaves before ${clash.name} ends at ${clash.end}. Change the start time, or that stop's time.`,
      );
    } else if (clash.kind === "midnight") {
      setProblem(
        `Moving the later stops ${formatMinutes(clash.minutes)} back would take ${clash.name} past midnight. Change the times.`,
      );
    } else if (clash.kind === "later") {
      setShifting(true);
    } else {
      void save();
    }
  };

  const save = async (shift?: number) => {
    if (!ready || !from || !to || !client) return;
    setBusy(true);
    setProblem(null);
    const transport = {
      mode,
      from_name: from.name,
      from_lat: from.lat,
      from_lon: from.lon,
      to_name: to.name,
      to_lat: to.lat,
      to_lon: to.lon,
      is_journey: journey,
      note: note.trim() ? note.trim() : null,
    };
    const startTime = startClock ? `${startClock}:00` : null;
    try {
      if (leg && existing) {
        const body: ItemUpdate = {
          transport,
          start_time: startTime,
          duration_minutes: length,
        };
        if (dayIndex !== existing.day.day_index) body.day_index = dayIndex;
        if (moved) body.position = position;
        if (shift) body.shift_later_minutes = shift;
        await call(
          client.PATCH("/v1/items/{item_id}", { params: { path: { item_id: leg.id } }, body }),
        );
      } else {
        const body: ItemCreate = {
          type: "transport",
          transport,
          start_time: startTime,
          duration_minutes: length,
          locked: true,
          position,
          ...(shift ? { shift_later_minutes: shift } : {}),
        };
        await call(
          client.POST("/v1/itineraries/{itinerary_id}/days/{day_index}/items", {
            params: { path: { itinerary_id: route.itineraryId, day_index: dayIndex } },
            body,
          }),
        );
      }
      setShifting(false);
      onDone();
    } catch (e) {
      setShifting(false);
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!leg || !client) return;
    setBusy(true);
    try {
      await callEmpty(
        client.DELETE("/v1/items/{item_id}", { params: { path: { item_id: leg.id } } }),
      );
      setRemoving(false);
      onDone();
    } catch (e) {
      setRemoving(false);
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const endField = (which: "from" | "to", label: string, value: End | null) => (
    <View style={styles.block}>
      <SelectField
        label={label}
        placeholder="Choose a stop or a city, or type a name"
        value={value?.name ?? null}
        detail={value && value.lat === null ? "Typed by you" : null}
        icon="pin"
        open={open === which}
        onToggle={() => {
          setOpen(open === which ? null : which);
          setTyping(null);
        }}
        testID={`leg-${which}`}
      >
        {options.map((o) => (
          <ChoiceRow
            key={o.key}
            title={o.name}
            meta={o.group}
            selected={value?.name === o.name && value.lat === o.lat}
            onPress={() => choose(which, { name: o.name, lat: o.lat, lon: o.lon })}
            testID={`leg-${which}-${o.key}`}
          />
        ))}
        <ChoiceRow
          title="Type a name"
          meta="A station, an airport, a port: no point on the map"
          icon="note"
          selected={false}
          onPress={() => {
            setOpen(null);
            setTyping(which);
            setTyped(value?.lat === null ? value.name : "");
          }}
          testID={`leg-${which}-type`}
        />
      </SelectField>
      {typing === which ? (
        <View style={styles.typedRow}>
          <View style={styles.typedField}>
            <TextField
              label={`${label}, typed`}
              value={typed}
              onChangeText={(t) => setTyped(t.slice(0, NAME_MAX))}
              testID={`leg-${which}-name`}
              autoFocus
            />
          </View>
          <Button
            label="Use"
            variant="secondary"
            size="sm"
            disabled={!typed.trim()}
            onPress={() => {
              choose(which, { name: typed.trim(), lat: null, lon: null });
              setTyping(null);
            }}
            testID={`leg-${which}-use`}
          />
        </View>
      ) : null}
    </View>
  );

  return (
    <KeyboardScrollView contentContainerStyle={styles.content}>
      <CompactHeader
        title={leg ? "Change transport" : "Add transport"}
        subtitle={trip.title}
        onBack={nav.back}
      />
      <Text style={styles.lead}>
        How you travel or travelled, as you enter it. Detour does not look up timetables: a length
        you leave out stays unknown.
      </Text>
      <View style={styles.pad}>
        <SelectField
          label="How"
          placeholder="Choose"
          value={MODE_LABEL[mode]}
          icon={MODE_ICON[mode]}
          open={open === "mode"}
          onToggle={() => setOpen(open === "mode" ? null : "mode")}
          testID="leg-mode"
        >
          {TRANSPORT_MODES.map((m) => (
            <ChoiceRow
              key={m}
              title={MODE_LABEL[m]}
              icon={MODE_ICON[m]}
              selected={m === mode}
              onPress={() => {
                setMode(m);
                setOpen(null);
              }}
              testID={`leg-mode-${m}`}
            />
          ))}
        </SelectField>

        {endField("from", "From", from)}
        {endField("to", "To", to)}

        <SelectField
          label="Day"
          placeholder="Choose a day"
          value={`Day ${dayIndex}`}
          detail={day?.base_city_name ?? null}
          icon="calendar"
          open={open === "day"}
          onToggle={() => setOpen(open === "day" ? null : "day")}
          testID="leg-day"
        >
          {sorted.map((d) => (
            <ChoiceRow
              key={d.id}
              title={`Day ${d.day_index}`}
              meta={d.base_city_name ?? undefined}
              selected={d.day_index === dayIndex}
              onPress={() => {
                setDayIndex(d.day_index);
                setOpen(null);
              }}
              testID={`leg-day-${d.day_index}`}
            />
          ))}
        </SelectField>

        <TimeField
          label="Leaves at"
          value={start}
          onChange={setStart}
          hint="Optional. 24-hour, like 10:12."
          testID="leg-start"
        />

        <SegmentedControl<"length" | "arrival">
          items={[
            { key: "length", label: "How long" },
            { key: "arrival", label: "Arrives at" },
          ]}
          value={lengthBy}
          onChange={setLengthBy}
          testID="leg-length-by"
        />
        {lengthBy === "length" ? (
          <View style={styles.lengthRow}>
            <View style={styles.typedField}>
              <DurationField
                label="How long"
                minutes={minutes}
                onChange={setMinutes}
                onValidity={setLengthValid}
                testID="leg-length"
              />
            </View>
            <Chip
              label="Not known"
              selected={minutes === null}
              onPress={() => {
                setMinutes(null);
                setLengthValid(true);
              }}
              testID="leg-length-unknown"
            />
          </View>
        ) : (
          <TimeField
            label="Arrives at"
            value={arrival}
            onChange={setArrival}
            hint="An arrival before the start is the next day."
            error={arrivalProblem}
            testID="leg-arrival"
          />
        )}
        <Text style={styles.small} testID="leg-length-said">
          {length === null ? `Length: ${NOT_ENTERED}` : `Length: ${formatMinutes(length)}`}
        </Text>

        {multiCity || journey ? (
          <Chip
            label="Journey between cities"
            icon="route"
            selected={journey}
            onPress={() => setJourney((j) => !j)}
            accessibilityLabel="Journey between cities: shown as the day's journey to its city"
            testID="leg-journey"
          />
        ) : null}

        <TextField
          label="Note"
          value={note}
          onChangeText={(t) => setNote(t.slice(0, NOTE_MAX))}
          multiline
          hint="Optional: a platform, a coach, a seat. A ticket belongs in Documents."
          testID="leg-note"
        />

        {problem ? <Notice tone="error">{problem}</Notice> : null}

        <Button
          label={leg ? "Save changes" : "Add transport"}
          fill
          loading={busy}
          disabled={!ready}
          onPress={attempt}
          testID="leg-save"
        />
        <Button label="Cancel" variant="secondary" fill onPress={nav.back} />
        {leg && existing ? (
          // A ticket or booking for this leg stays on the phone (ADR 023), linked by day and name.
          <Button
            label="Attach a document"
            variant="secondary"
            icon="document"
            fill
            onPress={() =>
              nav.push({
                name: "documentForm",
                tripId: trip.id,
                link: { kind: "leg", day: existing.day.day_index, name: leg.display_name },
                category: "transport",
              })
            }
            testID="leg-document"
          />
        ) : null}
        {leg ? (
          <Button
            label="Remove this transport"
            variant="ghost"
            tone="danger"
            onPress={() => setRemoving(true)}
            testID="leg-remove"
          />
        ) : null}
      </View>

      <ConfirmSheet
        visible={shifting && clash.kind === "later"}
        title="Move the later stops?"
        message={
          clash.kind === "later"
            ? `This ${MODE_LABEL[mode].toLowerCase()} runs until after ${clash.name} starts at ${clash.start}. Move ${clash.count === 1 ? "it" : `the ${clash.count} stops after it`} on day ${dayIndex} ${formatMinutes(clash.minutes)} later? Their order and lengths stay the same.`
            : ""
        }
        confirmLabel={
          clash.kind === "later"
            ? `Move ${clash.count === 1 ? "it" : "them"} ${formatMinutes(clash.minutes)} later`
            : "Move them"
        }
        cancelLabel="Change the times"
        busy={busy}
        onConfirm={() => void save(clash.kind === "later" ? clash.minutes : undefined)}
        onCancel={() => setShifting(false)}
      />
      <ConfirmSheet
        visible={removing}
        title="Remove this transport?"
        message={`${leg?.display_name ?? "It"} leaves the plan. Your stops stay as they are.`}
        confirmLabel="Yes, remove it"
        cancelLabel="Keep it"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(false)}
      />
    </KeyboardScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl, gap: layout.block },
  pad: { paddingHorizontal: layout.gutter, gap: spacing.md },
  lead: { ...type.label, color: colors.muted, paddingHorizontal: layout.gutter },
  label: { ...type.label, fontWeight: weight.semibold, color: colors.text },
  small: { ...type.caption, color: colors.muted },
  block: { gap: spacing.sm },
  typedRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm },
  typedField: { flex: 1 },
  lengthRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm },
});
