import type { CoverCandidate, DestinationResult, Trip } from "@detour/shared";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError, isOfflineError, planningIssues } from "../api/unwrap";
import { Button } from "../components/Button";
import { Cover } from "../components/ds/Cover";
import { CoverPicker } from "../components/ds/CoverPicker";
import {
  CitySearchSheet,
  StopList,
  type StopDraft,
  evenSplit,
  stopsProblem,
} from "../components/StopList";
import { Icon } from "../components/ds/Icon";
import { IconButton } from "../components/ds/primitives";
import { Notice, useAnnounceOnMount } from "../components/ui";
import { useTripActions } from "../data/actions";
import { useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { formatDate, isValidIsoDate, pluralise } from "../util/format";
import { CalendarSheet } from "../components/ds/Calendar";
import { localToday } from "../domain/trips";

export const SEARCH_DEBOUNCE_MS = 350;
export const MIN_QUERY_LENGTH = 2;
export const MAX_DAYS = 30;

type SearchState =
  | { phase: "idle" }
  | { phase: "searching" }
  | { phase: "done"; results: DestinationResult[] }
  | { phase: "error"; offline: boolean; message: string };

/** Why a result cannot be chosen, or null when it can. The backend decides (`unavailable_reason`). */
export function unavailableReason(r: DestinationResult): string | null {
  if (r.unavailable_reason === "area_single_city_only") {
    return "Areas in Japan cannot be planned yet (rail travel is not modelled). Choose a city.";
  }
  if (r.unavailable_reason === "region_not_available" || !r.planning_available) {
    return "Not available yet: this region's data has not been imported.";
  }
  return null;
}

function describeResult(r: DestinationResult): string {
  return [r.admin1_name, r.country_name].filter(Boolean).join(", ");
}

export type FormErrors = { date?: string };

export function validateForm(values: { startDate: string }): FormErrors {
  const errors: FormErrors = {};
  if (values.startDate.trim() && !isValidIsoDate(values.startDate.trim())) {
    errors.date = "Use the form YYYY-MM-DD, for example 2027-05-01.";
  }
  return errors;
}

export function CreateTripScreen() {
  const nav = useNavigation();
  const { state } = useBackend();
  const actions = useTripActions();

  const [query, setQuery] = useState("");
  // Answers by normalised query: a repeated query is answered from here without a request.
  const [found, setFound] = useState<Record<string, DestinationResult[]>>({});
  const [searchFailed, setSearchFailed] = useState<{
    key: string;
    offline: boolean;
    message: string;
  } | null>(null);
  const [chosen, setChosen] = useState<DestinationResult | null>(null);
  // A multi-city trip (ADR 024): the cities in the user's order with their days. Null while the
  // trip has one destination; "Add another city" starts it with the chosen city first.
  const [stops, setStops] = useState<StopDraft[] | null>(null);
  const [addingCity, setAddingCity] = useState(false);
  const [days, setDays] = useState(3);
  const [startDate, setStartDate] = useState("");
  const [calendar, setCalendar] = useState(false);
  // Saved for later (docs/design.md): chosen here, not sent, and the plans do not use them yet.
  const [style, setStyle] = useState<TravelStyle>("balanced");
  const [publicTransport, setPublicTransport] = useState(false);
  const [working, setWorking] = useState<"creating" | "planning" | "starting" | null>(null);
  const [mode, setMode] = useState<"generate" | "empty">("generate");
  const [problem, setProblem] = useState<{ message: string; issues: string[] } | null>(null);
  const [created, setCreated] = useState<Trip | null>(null);
  // "Change photo" (ADR 022 amendment): a candidate chosen before the trip exists is set as its
  // cover right after it is created.
  const [cover, setCoverChoice] = useState<CoverCandidate | null>(null);
  const [picker, setPicker] = useState(false);
  const apiUrl = (useBackend().apiUrl ?? "").replace(/\/$/, "");

  const client = state.phase === "ready" ? state.connection.client : null;
  const waking = state.phase === "connecting" && state.waking;

  // Destination search: debounced, at least two letters, the answer to a query is kept, and a
  // newer query makes an older answer irrelevant (the cleanup below).
  const q = query.trim();
  const key = q.toLowerCase();
  const needsSearch = !chosen && q.length >= MIN_QUERY_LENGTH && found[key] === undefined;
  useEffect(() => {
    if (!needsSearch || !client) return;
    let current = true;
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const response = await call(
            client.GET("/v1/destinations/search", { params: { query: { q, limit: 8 } } }),
          );
          if (!current) return;
          setSearchFailed(null);
          setFound((f) => ({ ...f, [key]: response.results }));
        } catch (e) {
          if (!current) return;
          setSearchFailed({ key, offline: isOfflineError(e), message: describeError(e) });
        }
      })();
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [needsSearch, client, q, key]);

  let search: SearchState;
  if (chosen || q.length < MIN_QUERY_LENGTH) search = { phase: "idle" };
  else if (found[key] !== undefined) search = { phase: "done", results: found[key] };
  else if (searchFailed?.key === key) search = { phase: "error", ...searchFailed };
  else if (!client && state.phase === "error")
    search = { phase: "error", offline: true, message: "Searching needs a connection." };
  else search = { phase: "searching" };

  const errors = validateForm({ startDate });
  const hasErrors = Object.keys(errors).length > 0;

  const planNow = async (trip: Trip) => {
    setWorking("planning");
    try {
      await actions.generate(trip.id);
      nav.replace({ name: "trip", tripId: trip.id });
    } catch (e) {
      setProblem({ message: describeError(e), issues: planningIssues(e) });
    } finally {
      setWorking(null);
    }
  };

  const startEmpty = async (trip: Trip) => {
    setWorking("starting");
    try {
      await actions.startEmptyTrip(trip.id);
      nav.replace({ name: "tripOverview", tripId: trip.id });
    } catch (e) {
      setProblem({ message: describeError(e), issues: [] });
    } finally {
      setWorking(null);
    }
  };

  const submit = async (how: "generate" | "empty") => {
    setProblem(null);
    setMode(how);
    if (!chosen || hasErrors) return;
    if (stops && stopsProblem(stops)) return;
    let trip = created;
    if (!trip) {
      setWorking("creating");
      try {
        trip = await actions.createTrip(
          stops
            ? {
                // The server names a multi-city trip after its cities ("Tokyo to Osaka").
                title: "Multi-city trip",
                destination_kind: "route",
                stops: stops.map((x) => ({ city_id: x.cityId, days: x.days })),
                duration_days: stops.reduce((n, x) => n + x.days, 0),
                start_date: startDate.trim() || null,
              }
            : {
                // The trip is named after its destination: the country, region or city.
                title: chosen.name,
                destination_kind: chosen.kind,
                destination_ref: chosen.ref,
                duration_days: days,
                start_date: startDate.trim() || null,
              },
        );
        setCreated(trip);
        if (cover) {
          // A cover that cannot be set leaves the automatic photo; the trip is not held up.
          trip = await actions.setCover(trip.id, cover.commons_file).catch(() => trip as Trip);
        }
      } catch (e) {
        setProblem({ message: describeError(e), issues: [] });
        setWorking(null);
        return;
      }
    }
    if (how === "empty") await startEmpty(trip);
    else await planNow(trip);
  };

  const offline = !actions.connected && state.phase === "error";

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.top}>
          <IconButton icon="back" label="Back" onPress={nav.back} />
        </View>
        <View style={styles.head}>
          <TitleText />
          <Text style={styles.subtitle}>
            Tell us where you want to go and we&apos;ll help you build the perfect itinerary.
          </Text>
        </View>

        {offline ? (
          <Notice tone="warning" label="Offline">
            Planning a trip needs a connection. Your saved trips can still be read.
          </Notice>
        ) : null}

        <View style={styles.section}>
          <View style={styles.row}>
            <Icon name="pin" size={22} color={colors.text} />
            <View style={styles.rowBody}>
              <Text style={styles.rowLabel}>Destination</Text>
              {chosen ? (
                <>
                  <Text style={styles.chosenName}>{chosen.name}</Text>
                  <Text style={styles.hint}>
                    {chosen.kind === "area" ? "Area" : "City"}
                    {describeResult(chosen) ? ` · ${describeResult(chosen)}` : ""}
                  </Text>
                </>
              ) : (
                <TextInput
                  testID="destination-input"
                  accessibilityLabel="Destination"
                  accessibilityHint="A city or an area in one of the imported regions, for example Vienna or Tyrol."
                  placeholder="City or area, for example Vienna"
                  placeholderTextColor={colors.muted}
                  value={query}
                  onChangeText={setQuery}
                  autoCorrect={false}
                  autoCapitalize="words"
                  returnKeyType="search"
                  style={styles.input}
                />
              )}
            </View>
            {chosen ? (
              <IconButton
                icon="close"
                label="Clear destination"
                onPress={() => {
                  setChosen(null);
                  setStops(null);
                  setCreated(null);
                  setCoverChoice(null);
                }}
              />
            ) : null}
          </View>
          {chosen?.kind === "area" ? (
            <Text style={styles.hint}>
              The plans choose base cities in the area and divide the days between them.
            </Text>
          ) : null}
          {!chosen ? (
            <SearchResults search={search} waking={waking} query={q} onChoose={setChosen} />
          ) : (
            <>
              <Cover
                seedKey={chosen.ref}
                uri={cover && apiUrl ? `${apiUrl}${cover.preview_url}` : null}
                height={120}
                rounded={radius.md}
                style={styles.cover}
                testID="create-cover"
              />
              <View style={styles.coverActions}>
                <Button
                  label="Change photo"
                  icon="photos"
                  variant="secondary"
                  size="compact"
                  hint="Choose the trip's photo from photos of the destination"
                  disabled={!actions.connected}
                  onPress={() => setPicker(true)}
                  testID="change-photo"
                />
                {cover ? (
                  <Text style={styles.hint} numberOfLines={1}>
                    Photo: {cover.credit.author}, {cover.credit.licence}
                  </Text>
                ) : null}
              </View>
              {chosen.kind === "city" ? (
                stops ? (
                  <StopList
                    stops={stops}
                    onChange={(next) => {
                      setCreated(null);
                      if (next.length >= 2) {
                        setStops(next);
                        return;
                      }
                      // One city left: an ordinary city trip of that city again.
                      const only = next[0];
                      setStops(null);
                      if (only) {
                        setDays(only.days);
                        if (String(only.cityId) !== chosen.ref) {
                          setChosen({ ...chosen, ref: String(only.cityId), name: only.name });
                        }
                      }
                    }}
                  />
                ) : (
                  <Button
                    label="Add another city"
                    icon="add"
                    variant="quiet"
                    size="compact"
                    hint="Plan a trip through several cities in your order"
                    onPress={() => setAddingCity(true)}
                    testID="add-city"
                  />
                )
              ) : null}
              {addingCity ? (
                <CitySearchSheet
                  onClose={() => setAddingCity(false)}
                  onChoose={(r) => {
                    setAddingCity(false);
                    setCreated(null);
                    const split = evenSplit(days, 2);
                    setStops([
                      {
                        cityId: Number(chosen.ref),
                        name: chosen.name,
                        detail: describeResult(chosen),
                        days: split[0] ?? 1,
                      },
                      {
                        cityId: Number(r.ref),
                        name: r.name,
                        detail: describeResult(r),
                        days: split[1] ?? 1,
                      },
                    ]);
                  }}
                />
              ) : null}
              {picker ? (
                <CoverPicker
                  visible
                  sources={
                    stops
                      ? stops.map((x) => ({
                          kind: "city" as const,
                          ref: String(x.cityId),
                          name: x.name,
                        }))
                      : [{ kind: chosen.kind, ref: chosen.ref, name: chosen.name }]
                  }
                  load={actions.coverCandidates}
                  chosen={cover?.commons_file ?? null}
                  onChoose={(c) => setCoverChoice(c)}
                  onClose={() => setPicker(false)}
                />
              ) : null}
            </>
          )}
        </View>

        <View style={styles.pair}>
          <View style={[styles.row, styles.half]}>
            <Icon name="calendar" size={22} color={colors.text} />
            <View style={styles.rowBody}>
              <Text style={styles.rowLabel}>Start date (optional)</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={
                  startDate ? `Start date, ${formatDate(startDate)}` : "Start date, not set"
                }
                accessibilityHint="Opens a calendar to choose the first day"
                onPress={() => setCalendar(true)}
                style={styles.dateButton}
                hitSlop={{ top: 8, bottom: 8 }}
                testID="start-date"
              >
                <Text style={[styles.input, !startDate && styles.placeholder]}>
                  {startDate ? formatDate(startDate).slice(4) : "Choose a date"}
                </Text>
              </Pressable>
            </View>
          </View>
          <View style={[styles.row, styles.half, styles.halfRule]}>
            <View style={styles.rowBody}>
              <Text style={styles.rowLabel}>Duration</Text>
              {stops ? (
                <Text style={styles.input} testID="route-total">
                  {pluralise(
                    stops.reduce((n, x) => n + x.days, 0),
                    "day",
                  )}
                </Text>
              ) : (
                <DaysStepper value={days} onChange={setDays} />
              )}
            </View>
          </View>
        </View>
        <CalendarSheet
          visible={calendar}
          value={startDate}
          today={localToday()}
          onPick={(iso) => {
            setStartDate(iso);
            setCalendar(false);
          }}
          onClear={() => {
            setStartDate("");
            setCalendar(false);
          }}
          onClose={() => setCalendar(false)}
        />

        <View style={styles.section}>
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            Travel style
          </Text>
          <View style={styles.chips} accessibilityRole="radiogroup">
            {TRAVEL_STYLES.map((t) => {
              const on = style === t.key;
              return (
                <Pressable
                  key={t.key}
                  accessibilityRole="radio"
                  accessibilityLabel={t.label}
                  accessibilityState={{ selected: on, checked: on }}
                  onPress={() => setStyle(t.key)}
                  style={[styles.chip, on && styles.chipOn]}
                  testID={`style-${t.key}`}
                >
                  <Text style={[styles.chipText, on && styles.chipTextOn]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={[styles.row, styles.transportRow]}>
          <Icon name="transport" size={22} color={colors.text} />
          <View style={styles.rowBody}>
            <Text style={styles.rowTitle}>Public transport</Text>
          </View>
          <Switch
            accessibilityLabel="Public transport"
            value={publicTransport}
            onValueChange={setPublicTransport}
            trackColor={{ true: colors.primary, false: colors.outline }}
            thumbColor={colors.surface}
            style={styles.switch}
          />
        </View>
        <Text style={styles.later}>
          Travel style and public transport are saved for later. The plans do not use them yet.
        </Text>

        {stops && stopsProblem(stops) ? (
          <Notice tone="warning" label="Cities">
            {stopsProblem(stops)}
          </Notice>
        ) : null}
        {problem ? (
          <Notice tone="error">
            {problem.message}
            {problem.issues.length > 0 ? ` ${problem.issues.join(" ")}` : ""}
            {created ? " The trip was saved; you can try again." : ""}
          </Notice>
        ) : null}
        {working === "planning" ? (
          <Notice tone="info" label="Planning">
            Choosing sights and working out travel times. This usually takes a few seconds.
          </Notice>
        ) : null}

        <View style={styles.actions}>
          <Button
            testID="empty-trip"
            label="Start with an empty trip"
            icon="add"
            variant="ink"
            fill
            loading={working !== null && mode === "empty"}
            disabled={
              !chosen ||
              offline ||
              (stops !== null && stopsProblem(stops) !== null) ||
              (working !== null && mode !== "empty")
            }
            hint={
              chosen ? "No proposals: you add the places yourself" : "Choose a destination first"
            }
            onPress={() => void submit("empty")}
          />
          <Button
            testID="plan-trip"
            label={
              created && problem && mode === "generate"
                ? "Try planning again"
                : "Suggest itineraries"
            }
            icon="route"
            variant="secondary"
            fill
            loading={working !== null && mode === "generate"}
            disabled={
              !chosen ||
              offline ||
              (stops !== null && stopsProblem(stops) !== null) ||
              (working !== null && mode !== "generate")
            }
            hint={
              chosen
                ? "Two different sightseeing plans to compare, with no restaurants"
                : "Choose a destination first"
            }
            onPress={() => void submit("generate")}
          />
          {created && problem ? (
            <Button
              label="Open the trip without a plan"
              variant="quiet"
              onPress={() => nav.replace({ name: "tripOverview", tripId: created.id })}
            />
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

type TravelStyle = "relaxed" | "balanced" | "active";
const TRAVEL_STYLES: { key: TravelStyle; label: string }[] = [
  { key: "relaxed", label: "Relaxed" },
  { key: "balanced", label: "Balanced" },
  { key: "active", label: "Active" },
];

function TitleText() {
  const ref = useAnnounceOnMount();
  return (
    <View ref={ref} accessible accessibilityRole="header" accessibilityLabel="Create new trip">
      <Text style={styles.title}>Create new trip</Text>
    </View>
  );
}

function DaysStepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const text = pluralise(value, "day");
  return (
    <View style={styles.stepper}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Fewer days"
        accessibilityState={{ disabled: value <= 1 }}
        disabled={value <= 1}
        onPress={() => onChange(value - 1)}
        style={styles.stepButton}
      >
        <Text style={[styles.stepText, value <= 1 && styles.stepOff]}>−</Text>
      </Pressable>
      <View
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel="Days"
        accessibilityValue={{ min: 1, max: MAX_DAYS, now: value, text }}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(e) => {
          if (e.nativeEvent.actionName === "increment" && value < MAX_DAYS) onChange(value + 1);
          if (e.nativeEvent.actionName === "decrement" && value > 1) onChange(value - 1);
        }}
      >
        <Text style={styles.stepValue}>{text}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="More days"
        accessibilityState={{ disabled: value >= MAX_DAYS }}
        disabled={value >= MAX_DAYS}
        onPress={() => onChange(value + 1)}
        style={styles.stepButton}
      >
        <Text style={[styles.stepText, value >= MAX_DAYS && styles.stepOff]}>+</Text>
      </Pressable>
    </View>
  );
}

function SearchResults({
  search,
  waking,
  query,
  onChoose,
}: {
  search: SearchState;
  waking: boolean;
  query: string;
  onChoose: (r: DestinationResult) => void;
}) {
  if (search.phase === "idle") {
    return query.length === 0 ? null : (
      <Text style={styles.hint}>Type at least {MIN_QUERY_LENGTH} letters.</Text>
    );
  }
  if (search.phase === "searching") {
    return (
      <Text style={styles.hint} accessibilityLiveRegion="polite">
        {waking ? "Waking the server. This can take about a minute…" : "Searching…"}
      </Text>
    );
  }
  if (search.phase === "error") {
    return (
      <Notice
        tone={search.offline ? "warning" : "error"}
        label={search.offline ? "Offline" : "Problem"}
      >
        {search.offline ? "Searching needs a connection." : search.message}
      </Notice>
    );
  }
  if (search.results.length === 0) {
    return (
      <Text style={styles.hint} accessibilityLiveRegion="polite">
        No place matches “{query}”. Try another spelling. Only the imported regions can be planned.
      </Text>
    );
  }
  return (
    <View style={styles.results} accessibilityLiveRegion="polite">
      {search.results.map((r) => {
        const reason = unavailableReason(r);
        return (
          <Pressable
            key={`${r.kind}:${r.ref}`}
            testID={`destination-result-${r.ref}`}
            accessibilityRole="button"
            accessibilityLabel={`${r.name}${describeResult(r) ? `, ${describeResult(r)}` : ""}. ${r.kind === "city" ? "City" : "Area"}.${reason ? ` ${reason}` : ""}`}
            accessibilityState={{ disabled: reason !== null }}
            disabled={reason !== null}
            onPress={() => onChoose(r)}
            style={({ pressed }) => [
              styles.result,
              reason !== null && styles.resultDisabled,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.resultName}>{r.name}</Text>
            <Text style={styles.resultMeta}>
              {r.kind === "city" ? "City" : "Area"}
              {describeResult(r) ? ` · ${describeResult(r)}` : ""}
            </Text>
            {reason ? <Text style={styles.reason}>{reason}</Text> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const RULE = StyleSheet.hairlineWidth;

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  top: { paddingHorizontal: spacing.sm, paddingTop: spacing.sm },
  head: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, gap: spacing.xs },
  title: { ...type.display, color: colors.text },
  subtitle: { ...type.body, color: colors.muted },
  section: { paddingHorizontal: spacing.lg, gap: spacing.md, marginBottom: spacing.lg },
  sectionTitle: { ...type.heading, color: colors.text },
  // A field is an icon, a small label and a value over a hairline: no boxes.
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: TOUCH + 12,
    paddingVertical: spacing.sm,
    borderBottomWidth: RULE,
    borderBottomColor: colors.border,
  },
  rowBody: { flex: 1, gap: 2 },
  rowLabel: { ...type.caption, color: colors.muted },
  rowTitle: { ...type.body, color: colors.text },
  input: { ...type.body, color: colors.text, minHeight: 32, paddingVertical: 0 },
  dateButton: { minHeight: 32, justifyContent: "center" },
  placeholder: { color: colors.muted },
  chosenName: { ...type.heading, color: colors.text },
  cover: { marginTop: spacing.xs },
  coverActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  pair: {
    flexDirection: "row",
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
  },
  half: { flex: 1, borderBottomWidth: RULE },
  halfRule: { marginLeft: spacing.lg },
  hint: { ...type.small, color: colors.muted },
  error: {
    ...type.small,
    color: colors.errorText,
    fontWeight: "600",
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  results: { gap: 0 },
  result: {
    minHeight: TOUCH + 8,
    borderBottomWidth: RULE,
    borderBottomColor: colors.border,
    paddingVertical: spacing.md,
    gap: 2,
  },
  resultDisabled: { opacity: 0.7 },
  pressed: { opacity: 0.85 },
  resultName: { ...type.heading, color: colors.text },
  resultMeta: { ...type.small, color: colors.muted },
  reason: { ...type.small, color: colors.errorText, fontWeight: "600" },

  chips: { flexDirection: "row", gap: spacing.sm },
  chip: {
    flex: 1,
    minHeight: TOUCH,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.outline,
  },
  chipOn: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  chipText: { ...type.small, color: colors.text },
  chipTextOn: { fontWeight: "700", color: colors.primary },
  transportRow: {
    marginHorizontal: spacing.lg,
    borderTopWidth: RULE,
    borderTopColor: colors.border,
  },
  switch: { minHeight: TOUCH },
  later: {
    ...type.caption,
    color: colors.muted,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: spacing.lg,
  },
  actions: { paddingHorizontal: spacing.lg, gap: spacing.md },

  stepper: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  stepButton: { width: 36, minHeight: TOUCH, alignItems: "center", justifyContent: "center" },
  stepText: { fontSize: 24, color: colors.text },
  stepOff: { color: colors.outline },
  stepValue: { ...type.body, color: colors.text, minWidth: 64, textAlign: "center" },
});
