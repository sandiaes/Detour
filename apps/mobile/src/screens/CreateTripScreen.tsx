import type { CoverCandidate, DestinationResult, Trip } from "@detour/shared";
import { useEffect, useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError, isOfflineError, planningIssues } from "../api/unwrap";
import {
  Button,
  ChoiceRow,
  DropdownPanel,
  InlineStatus,
  ListRow,
  Notice,
  ScreenHeader,
  SearchField,
  SelectField,
  Stepper,
  TextField,
  KeyboardScrollView,
} from "../components/ds";
import { Cover } from "../components/ds/Cover";
import { CoverPicker } from "../components/ds/CoverPicker";
import {
  CitySearchSheet,
  StopList,
  type StopDraft,
  evenSplit,
  stopsProblem,
} from "../components/StopList";
import { useTripActions } from "../data/actions";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, radius, size as sizes, spacing, type, weight } from "../theme";
import { formatDate, isValidIsoDate, pluralise } from "../util/format";
import { CalendarSheet } from "../components/ds/Calendar";
import { localToday } from "../domain/trips";
import {
  type Choice,
  choiceFromExternal,
  isPlannable,
  manualChoice,
  manualPoint,
  notPlannableReason,
  tripBody,
} from "../domain/destinations";

export const SEARCH_DEBOUNCE_MS = 350;
export const MIN_QUERY_LENGTH = 2;
export const MAX_DAYS = 30;

type SearchState =
  | { phase: "idle" }
  | { phase: "searching" }
  | { phase: "done"; results: Choice[] }
  | { phase: "error"; offline: boolean; message: string };

/** Why suggestions are not offered for a result, or null when they are (ADR 027: the result can
 * still be chosen, as an empty trip). */
export function unavailableReason(r: DestinationResult): string | null {
  return notPlannableReason(r);
}

function describeResult(r: Choice): string {
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
  const [chosen, setChosen] = useState<Choice | null>(null);
  // "Search more widely" (ADR 027): Photon results by normalised query, "none" when it found
  // nothing, "unavailable" when it could not be asked. Typed coordinates of a manual destination.
  const [wide, setWide] = useState<Record<string, Choice[] | "none" | "unavailable">>({});
  const [manualLat, setManualLat] = useState("");
  const [manualLon, setManualLon] = useState("");
  // A multi-city trip (ADR 024): the cities in the user's order with their days. Null while the
  // trip has one destination; "Add another city" starts it with the chosen city first.
  const [stops, setStops] = useState<StopDraft[] | null>(null);
  const [addingCity, setAddingCity] = useState(false);
  const [days, setDays] = useState(3);
  const [startDate, setStartDate] = useState("");
  const [calendar, setCalendar] = useState(false);
  // Saved for later (docs/design.md): chosen here, not sent, and the plans do not use it yet.
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

  const searchWider = async () => {
    if (!client) return;
    try {
      const response = await call(
        client.GET("/v1/destinations/search", {
          params: { query: { q, limit: 8, include_external: true, also_if_found: true } },
        }),
      );
      const places = (response.external.results ?? [])
        .map(choiceFromExternal)
        .filter((c): c is Choice => c !== null);
      const state =
        places.length > 0
          ? places
          : response.external.state === "ok" || response.external.state === "cached"
            ? "none"
            : "unavailable";
      setWide((w) => ({ ...w, [key]: state }));
    } catch {
      setWide((w) => ({ ...w, [key]: "unavailable" }));
    }
  };

  let search: SearchState;
  if (chosen || q.length < MIN_QUERY_LENGTH) search = { phase: "idle" };
  else if (found[key] !== undefined) search = { phase: "done", results: found[key] };
  else if (searchFailed?.key === key) search = { phase: "error", ...searchFailed };
  else if (!client && state.phase === "error")
    search = { phase: "error", offline: true, message: "Searching needs a connection." };
  else search = { phase: "searching" };

  // A manual destination needs both typed coordinates before anything is created.
  const manual = chosen?.ref === "manual";
  const point = manual ? manualPoint(manualLat, manualLon) : null;
  const needsPoint = manual && point === null;
  const plannable = chosen !== null && isPlannable(chosen);
  const hasPhotos =
    chosen !== null && !(chosen.kind === "place" && !chosen.ref.startsWith("geonames:"));
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
    if (!chosen || hasErrors || needsPoint) return;
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
            : // The trip is named after its destination: the country, region or city. A place
              // with no sight data is an empty trip whose destination is a snapshot (ADR 027).
              tripBody(
                point ? { ...chosen, ...point } : chosen,
                { days, startDate: startDate.trim() || null },
                !isPlannable(chosen),
              ),
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
  const clearDestination = () => {
    setChosen(null);
    setStops(null);
    setCreated(null);
    setCoverChoice(null);
  };
  return (
    <View style={styles.fill}>
      <KeyboardScrollView contentContainerStyle={styles.content}>
        <ScreenHeader
          title="Create new trip"
          subtitle="Choose where you want to go; Detour helps you build the itinerary."
          onBack={nav.back}
        />
        <View style={styles.body}>
          {offline ? (
            <Notice tone="warning" label="Offline">
              Planning a trip needs a connection. Your saved trips can still be read.
            </Notice>
          ) : null}
          <View style={styles.block}>
            {chosen ? (
              <SelectField
                label="Destination"
                placeholder="Any place"
                icon={chosen.kind === "city" ? "city" : "pin"}
                value={chosen.name}
                detail={`${chosen.kind === "area" ? "Area" : chosen.kind === "place" ? "Place" : "City"}${describeResult(chosen) ? ` · ${describeResult(chosen)}` : ""}`}
                onClear={clearDestination}
                clearLabel="Clear destination"
              />
            ) : (
              <SearchField
                label="Destination"
                testID="destination-input"
                accessibilityLabel="Destination"
                accessibilityHint="Any place, for example Vienna, Tyrol or Hallstatt."
                placeholder="Any place, for example Vienna"
                value={query}
                onChangeText={setQuery}
                onClear={() => setQuery("")}
                autoCapitalize="words"
              />
            )}
            {chosen?.kind === "area" && plannable ? (
              <Text style={styles.hint}>
                The plans choose base cities in the area and divide the days between them.
              </Text>
            ) : null}
            {chosen && !plannable ? (
              <Text style={styles.hint} testID="not-plannable">
                {notPlannableReason(chosen)}
              </Text>
            ) : null}
            {manual ? (
              <View style={styles.pair}>
                <View style={styles.half}>
                  <TextField
                    label="Latitude"
                    testID="manual-lat"
                    accessibilityLabel="Latitude"
                    placeholder="e.g. 47.5622"
                    value={manualLat}
                    onChangeText={setManualLat}
                    keyboardType="numbers-and-punctuation"
                  />
                </View>
                <View style={styles.half}>
                  <TextField
                    label="Longitude"
                    testID="manual-lon"
                    accessibilityLabel="Longitude"
                    placeholder="e.g. 13.6493"
                    value={manualLon}
                    onChangeText={setManualLon}
                    keyboardType="numbers-and-punctuation"
                  />
                </View>
              </View>
            ) : null}
            {!chosen ? (
              <SearchResults
                search={search}
                waking={waking}
                query={q}
                onChoose={setChosen}
                wide={wide[key]}
                onWiden={() => void searchWider()}
                onManual={() => setChosen(manualChoice(q))}
                online={client !== null}
              />
            ) : (
              <>
                <Cover
                  seedKey={chosen.ref}
                  uri={cover && apiUrl ? `${apiUrl}${cover.preview_url}` : null}
                  height={120}
                  rounded={radius.lg}
                  testID="create-cover"
                />
                {hasPhotos ? (
                  <View style={styles.row}>
                    <Button
                      label="Change photo"
                      icon="photos"
                      variant="secondary"
                      size="sm"
                      hint="Choose the trip's photo from photos of the destination"
                      disabled={!actions.connected}
                      onPress={() => setPicker(true)}
                      testID="change-photo"
                    />
                    {cover ? (
                      <Text style={styles.credit} numberOfLines={1}>
                        Photo: {cover.credit.author}, {cover.credit.licence}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {chosen.kind === "city" && plannable ? (
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
                      variant="ghost"
                      size="sm"
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
                        : [
                            {
                              kind: chosen.kind === "area" ? ("area" as const) : ("city" as const),
                              ref: chosen.ref.replace(/^geonames:/, ""),
                              name: chosen.name,
                            },
                          ]
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
            <View style={styles.half}>
              <SelectField
                label="Start date (optional)"
                placeholder="Choose a date"
                icon="calendar"
                value={startDate ? formatDate(startDate).slice(4) : null}
                accessibilityLabel={
                  startDate ? `Start date, ${formatDate(startDate)}` : "Start date, not set"
                }
                accessibilityHint="Opens a calendar to choose the first day"
                onPress={() => setCalendar(true)}
                testID="start-date"
              />
            </View>
            <View style={styles.half}>
              <Text style={styles.label}>Duration</Text>
              <View style={styles.duration}>
                {stops ? (
                  <Text style={styles.total} testID="route-total">
                    {pluralise(
                      stops.reduce((n, x) => n + x.days, 0),
                      "day",
                    )}
                  </Text>
                ) : (
                  <Stepper
                    value={days}
                    min={1}
                    max={MAX_DAYS}
                    onChange={setDays}
                    format={(n) => pluralise(n, "day")}
                    accessibilityLabel="Days"
                    decreaseLabel="Fewer days"
                    increaseLabel="More days"
                  />
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

          <ListRow
            icon="transport"
            title="Public transport"
            detail="Saved for later. The plans do not use it yet."
            inset="none"
            trailing={
              <Switch
                accessibilityLabel="Public transport"
                value={publicTransport}
                onValueChange={setPublicTransport}
                trackColor={{ true: colors.primary, false: colors.outline }}
                thumbColor={colors.surface}
              />
            }
          />

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
              label="Start a fresh trip"
              icon="add"
              fill
              loading={working !== null && mode === "empty"}
              disabled={
                !chosen ||
                needsPoint ||
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
                  : "Generate itineraries"
              }
              icon="route"
              variant="secondary"
              fill
              loading={working !== null && mode === "generate"}
              disabled={
                !chosen ||
                !plannable ||
                offline ||
                (stops !== null && stopsProblem(stops) !== null) ||
                (working !== null && mode !== "generate")
              }
              hint={
                !chosen
                  ? "Choose a destination first"
                  : !plannable
                    ? (notPlannableReason(chosen) ?? "")
                    : "Two different sightseeing plans to compare, with no restaurants"
              }
              onPress={() => void submit("generate")}
            />
            {created && problem ? (
              <Button
                label="Open the trip without a plan"
                variant="ghost"
                size="sm"
                onPress={() => nav.replace({ name: "tripOverview", tripId: created.id })}
              />
            ) : null}
          </View>
        </View>
      </KeyboardScrollView>
    </View>
  );
}

function ResultRow({ r, onChoose }: { r: Choice; onChoose: (r: Choice) => void }) {
  const reason = notPlannableReason(r);
  const kind = r.kind === "city" ? "City" : r.kind === "area" ? "Area" : "Place";
  return (
    <ChoiceRow
      testID={`destination-result-${r.ref}`}
      icon={r.kind === "city" ? "city" : "pin"}
      title={r.name}
      meta={[`${kind}${describeResult(r) ? ` · ${describeResult(r)}` : ""}`, reason]
        .filter(Boolean)
        .join(" · ")}
      selected={false}
      accessibilityLabel={`${r.name}${describeResult(r) ? `, ${describeResult(r)}` : ""}. ${kind}.${reason ? ` ${reason}` : ""}`}
      onPress={() => onChoose(r)}
    />
  );
}

function SearchResults({
  search,
  waking,
  query,
  onChoose,
  wide,
  onWiden,
  onManual,
  online,
}: {
  search: SearchState;
  waking: boolean;
  query: string;
  onChoose: (r: Choice) => void;
  wide: Choice[] | "none" | "unavailable" | undefined;
  onWiden: () => void;
  onManual: () => void;
  online: boolean;
}) {
  if (search.phase === "idle") {
    return query.length === 0 ? null : (
      <InlineStatus text={`Type at least ${MIN_QUERY_LENGTH} letters.`} />
    );
  }
  if (search.phase === "searching") {
    return (
      <InlineStatus
        busy
        text={waking ? "Waking the server. This can take about a minute…" : "Searching…"}
      />
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
  const more = Array.isArray(wide) ? wide : [];
  return (
    <View style={styles.results}>
      {search.results.length === 0 && wide === undefined ? (
        <InlineStatus
          text={`Nothing in the imported data matches “${query}”. Search more widely to find any place.`}
        />
      ) : null}
      {search.results.length + more.length > 0 ? (
        <DropdownPanel testID="destination-results">
          {search.results.map((r) => (
            <ResultRow key={`${r.kind}:${r.ref}`} r={r} onChoose={onChoose} />
          ))}
          {more.map((r) => (
            <ResultRow key={r.ref} r={r} onChoose={onChoose} />
          ))}
        </DropdownPanel>
      ) : null}
      {wide === "none" ? <InlineStatus text={`No wider result for “${query}”.`} /> : null}
      {wide === "unavailable" ? (
        <InlineStatus text="The wider search is not available right now. You can still enter the place by hand." />
      ) : null}
      <View style={styles.row}>
        {wide === undefined ? (
          <Button
            testID="search-wider"
            label="Search more widely"
            icon="search"
            variant="secondary"
            size="sm"
            hint="Look for any place in the world, not only the imported regions"
            disabled={!online}
            onPress={onWiden}
          />
        ) : null}
        <Button
          testID="enter-by-hand"
          label="Enter it by hand"
          variant="ghost"
          size="sm"
          hint="Type the name and the coordinates yourself"
          onPress={onManual}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  body: { paddingHorizontal: layout.gutter, gap: layout.section },
  block: { gap: layout.block },
  label: { ...type.caption, color: colors.muted, fontWeight: weight.medium },
  hint: { ...type.caption, color: colors.muted },
  credit: { ...type.caption, color: colors.muted, flexShrink: 1 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  pair: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  half: { flex: 1, gap: spacing.xs },
  duration: { minHeight: sizes.control, justifyContent: "center" },
  total: { ...type.body, color: colors.text },
  results: { gap: spacing.sm },
  actions: { gap: spacing.sm },
});
