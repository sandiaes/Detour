import type {
  ChangeSetCreate,
  DestinationResult,
  ExternalPlace,
  Itinerary,
  PlaceSuggestionRequest,
  PlaceSuggestions,
  PlaceSummary,
  Trip,
} from "@detour/shared";
import { Camera, Map, Marker } from "@maplibre/maplibre-react-native";
import { type ReactNode, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError, planningIssues } from "../api/unwrap";
import { AttributionBar } from "../components/AttributionBar";
import { Button } from "../components/Button";
import { ChooseSlot, type ChosenSlot } from "../components/ChooseSlot";
import { Icon, type IconName } from "../components/ds/Icon";
import { Tabs } from "../components/ds/primitives";
import { SuggestionCard } from "../components/ds/SuggestionCard";
import { Chip, Field, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import {
  affectedLines,
  placeSuggestionSentence,
  placeSuggestionTitle,
  placeSuggestionWhere,
  travelImpact,
} from "../domain/placeSuggestions";
import { type Route, useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { formatMeters, formatMinutes } from "../util/format";

// Adding a place (Phase 7, ADR 018; redesigned in ADR 021, step 4). Find it (sights, towns and
// towns, an address, or a pin), say how long to stay, and Detour's
// recalculation suggests up to three days with the time, the travel it adds and what else moves.
// The chosen day is previewed with its full diff; nothing changes until the user accepts.

type AddRoute = Extract<Route, { name: "addPlace" }>;

export const SEARCH_DEBOUNCE_MS = 350;
const MIN_QUERY = 2;
/** Sights are searched within this distance of the trip's destination. */
export const SIGHT_RADIUS_M = 50_000;
export const DURATIONS = [30, 60, 90, 120, 180] as const;

/** What the user picked: an imported sight, a town, an external result (a search or an address)
 * or a pin. */
export type Choice =
  | { kind: "sight"; place: PlaceSummary }
  | { kind: "town"; town: DestinationResult }
  | { kind: "external"; place: ExternalPlace }
  | { kind: "pin"; lat: number; lon: number };

type Mode = "search" | "address" | "pin";
type Results = {
  sights: PlaceSummary[];
  towns: DestinationResult[];
};

/** "Hauptplatz 1, 8010 Graz, Austria" from an external result's parts. */
export function externalAddress(p: ExternalPlace): string {
  const street = [p.street, p.housenumber].filter(Boolean).join(" ");
  const town = [p.postcode, p.city].filter(Boolean).join(" ");
  return [street, town, p.country].filter(Boolean).join(", ");
}

function choiceName(c: Choice, customName: string): string {
  if (customName.trim()) return customName.trim();
  switch (c.kind) {
    case "sight":
      return c.place.name ?? c.place.category;
    case "town":
      return c.town.name;
    case "external":
      return c.place.name;
    case "pin":
      return "";
  }
}

/** The place for the suggestion and preview requests, saving it as one of the user's places
 * first when it is not an imported sight. */
export async function placeFor(
  choice: Choice,
  minutes: number | null,
  name: string,
  savePlace: ReturnType<typeof useChangeActions>["savePlace"],
): Promise<PlaceSuggestionRequest> {
  if (choice.kind === "sight") {
    return { place_id: choice.place.id, ...(minutes ? { duration_minutes: minutes } : {}) };
  }
  const base =
    choice.kind === "town"
      ? {
          kind: "city" as const,
          name: choice.town.name,
          lat: choice.town.lat,
          lon: choice.town.lon,
          source: "search_result" as const,
          search_provider: "geonames" as const,
          search_ref: choice.town.ref,
        }
      : choice.kind === "external"
        ? {
            kind: "location" as const,
            name: name.trim() || choice.place.name,
            lat: choice.place.lat,
            lon: choice.place.lon,
            ...(choice.place.ref
              ? {
                  source: "search_result" as const,
                  search_provider: "photon" as const,
                  search_ref: choice.place.ref,
                }
              : { source: "manual_pin" as const }),
          }
        : {
            kind: "location" as const,
            name: name.trim(),
            lat: choice.lat,
            lon: choice.lon,
            source: "manual_pin" as const,
          };
  const place = await savePlace(base);
  return { user_place_id: place.id, duration_minutes: minutes ?? 60 };
}

/** The change-set body for a choice (kept for the callers of Phase 7). */
export async function bodyFor(
  choice: Choice,
  minutes: number | null,
  pinName: string,
  savePlace: ReturnType<typeof useChangeActions>["savePlace"],
): Promise<ChangeSetCreate> {
  return { action: "add_place", ...(await placeFor(choice, minutes, pinName, savePlace)) };
}

export function AddPlaceScreen({ route }: { route: AddRoute }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const changes = useChangeActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === route.tripId);
  const itinerary = useResource<Itinerary>(keys.itinerary(route.itineraryId), (c) =>
    call(
      c.GET("/v1/itineraries/{itinerary_id}", {
        params: { path: { itinerary_id: route.itineraryId } },
      }),
    ),
  );
  // An empty (manual) plan cannot be recalculated, so it has no suggestions: the day and time
  // are chosen directly. On a planned one, the user may still choose.
  const isManual = itinerary.data?.profile === "manual";
  const [how, setHow] = useState<"suggest" | "choose">("suggest");
  const choosing = isManual || how === "choose";
  const client = state.phase === "ready" ? state.connection.client : null;
  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;

  const [mode, setMode] = useState<Mode>("search");
  const [query, setQuery] = useState("");
  const [address, setAddress] = useState("");
  const [results, setResults] = useState<Record<string, Results>>({});
  const [wide, setWide] = useState<Record<string, ExternalPlace[] | "none">>({});
  const [addressResults, setAddressResults] = useState<ExternalPlace[] | "none" | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [customName, setCustomName] = useState("");
  const [minutes, setMinutes] = useState<number | null>(null);
  const [request, setRequest] = useState<PlaceSuggestionRequest | null>(null);
  // The user place saved for a town, address or pin, so asking again does not save it twice.
  const [savedId, setSavedId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<PlaceSuggestions | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [working, setWorking] = useState<"find" | "preview" | "address" | null>(null);
  const [problem, setProblem] = useState<{ message: string; issues: string[] } | null>(null);

  const q = query.trim();
  const key = q.toLowerCase();
  const centre = trip?.destination;
  const needsSearch = mode === "search" && q.length >= MIN_QUERY && results[key] === undefined;
  useEffect(() => {
    if (!needsSearch || !client || !centre) return;
    let current = true;
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const near = { lat: centre.lat, lon: centre.lon, radius_m: SIGHT_RADIUS_M, limit: 8 };
          const [sights, towns] = await Promise.all([
            call(
              client.GET("/v1/places/search", {
                params: { query: { q, kind: "attraction", ...near } },
              }),
            ),
            call(client.GET("/v1/destinations/search", { params: { query: { q, limit: 5 } } })),
          ]);
          if (!current) return;
          setSearchError(null);
          setResults((r) => ({
            ...r,
            [key]: {
              sights: sights.results.filter((p) => p.name),
              towns: towns.results.filter((t) => t.kind === "city"),
            },
          }));
        } catch (e) {
          if (current) setSearchError(describeError(e));
        }
      })();
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [needsSearch, client, centre, q, key]);

  /** Places beyond the imported data, and addresses: Photon through the Detour server. */
  const external = async (text: string): Promise<ExternalPlace[]> => {
    if (!client || !centre) return [];
    const response = await call(
      client.GET("/v1/places/search", {
        params: {
          query: { q: text, lat: centre.lat, lon: centre.lon, limit: 8, include_external: true },
        },
      }),
    );
    return response.external.results ?? [];
  };

  const searchWider = async () => {
    try {
      const found = await external(q);
      setWide((w) => ({ ...w, [key]: found.length ? found : "none" }));
    } catch (e) {
      setSearchError(describeError(e));
    }
  };

  const findAddress = async () => {
    setWorking("address");
    setSearchError(null);
    try {
      const found = await external(address.trim());
      setAddressResults(found.length ? found : "none");
    } catch (e) {
      setSearchError(describeError(e));
    } finally {
      setWorking(null);
    }
  };

  const clearSuggestions = () => {
    setSuggestions(null);
    setRequest(null);
    setPicked(null);
    setProblem(null);
  };

  const pick = (c: Choice) => {
    setChoice(c);
    setSavedId(null);
    clearSuggestions();
    setCustomName(c.kind === "external" && mode === "address" ? c.place.name : "");
    // A sight has a typical length; anything else needs one from the user.
    setMinutes(c.kind === "sight" ? null : c.kind === "town" ? 120 : 60);
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    setChoice(null);
    clearSuggestions();
  };

  const named = choice !== null && (choice.kind !== "pin" || customName.trim().length > 0);
  const ready = named && working === null && changes.connected;

  const find = async () => {
    if (!choice) return;
    setWorking("find");
    clearSuggestions();
    try {
      const body =
        choice.kind !== "sight" && savedId
          ? { user_place_id: savedId, duration_minutes: minutes ?? 60 }
          : await placeFor(choice, minutes, customName, changes.savePlace);
      if (body.user_place_id) setSavedId(body.user_place_id);
      setRequest(body);
      const found = await changes.suggestPlaces(route.itineraryId, body);
      setSuggestions(found);
      setPicked(found.suggestions.length ? 0 : null);
    } catch (e) {
      setProblem({ message: describeError(e), issues: planningIssues(e) });
    } finally {
      setWorking(null);
    }
  };

  const preview = async () => {
    const chosen = picked !== null ? suggestions?.suggestions[picked] : undefined;
    if (!request || !chosen) return;
    setWorking("preview");
    setProblem(null);
    try {
      const change = await changes.preview(route.itineraryId, {
        action: "add_place",
        ...request,
        day: chosen.day,
      });
      nav.replace({
        name: "changePreview",
        tripId: route.tripId,
        itineraryId: route.itineraryId,
        changeSetId: change.id,
      });
    } catch (e) {
      setProblem({ message: describeError(e), issues: planningIssues(e) });
    } finally {
      setWorking(null);
    }
  };

  /** Adds the chosen place at the day and time the user picked, with no proposal. */
  const addAt = async (slot: ChosenSlot) => {
    if (!choice) return;
    setWorking("preview");
    setProblem(null);
    try {
      const ref = await placeFor(choice, slot.minutes, customName, changes.savePlace);
      await changes.addItem(route.tripId, route.itineraryId, slot.day, {
        type: "visit",
        place_id: ref.place_id ?? null,
        user_place_id: ref.user_place_id ?? null,
        start_time: slot.time,
        duration_minutes: slot.minutes,
        position: slot.position,
        locked: false,
      });
      nav.back();
    } catch (e) {
      setProblem({ message: describeError(e), issues: planningIssues(e) });
    } finally {
      setWorking(null);
    }
  };

  const found = results[key];
  const wider = wide[key];
  const nothingFound = found !== undefined && found.sights.length === 0 && found.towns.length === 0;

  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <ScreenHeader
        title="Add a place"
        subtitle={trip ? `${trip.title} · ${trip.destination.name}` : undefined}
        onBack={nav.back}
      />
      <View style={styles.section}>
        <Text style={styles.lead}>
          Find a sight or a town, or add your own by address or pin. Detour suggests the best days
          for it and shows what would change before anything changes.
        </Text>
      </View>
      <Tabs<Mode>
        items={[
          { key: "search", label: "Search" },
          { key: "address", label: "Address" },
          { key: "pin", label: "Pin on map" },
        ]}
        value={mode}
        onChange={switchMode}
        testID="add-mode"
      />

      <View style={styles.body}>
        {mode === "search" ? (
          <View style={styles.gap}>
            <Field
              label="Sight or town"
              value={query}
              onChangeText={(t) => {
                setQuery(t);
                setChoice(null);
                clearSuggestions();
              }}
              autoCorrect={false}
              hint="At least two letters. Places near the trip and towns are searched first."
            />
            {searchError ? <Notice tone="error">{searchError}</Notice> : null}
            {q.length >= MIN_QUERY && found === undefined && !searchError ? (
              <Text style={styles.muted}>Searching…</Text>
            ) : null}
            {found?.sights.length ? (
              <ResultGroup title="Sights">
                {found.sights.map((p) => (
                  <ResultRow
                    key={p.id}
                    icon="sight"
                    title={p.names?.display ?? p.name_en ?? p.name ?? p.category}
                    meta={[
                      // The English name leads; the name used locally stays visible beside it
                      // (ADR 025), and a name Detour romanized itself says so.
                      p.names ? p.names.local : p.name_en ? p.name : null,
                      p.names?.auto_generated ? "automatically romanized" : null,
                      p.category.replace(/_/g, " "),
                      p.city_name,
                      p.distance_m != null
                        ? `${formatMeters(p.distance_m)} from ${centre?.name ?? "the centre"}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    selected={choice?.kind === "sight" && choice.place.id === p.id}
                    onPress={() => pick({ kind: "sight", place: p })}
                  />
                ))}
              </ResultGroup>
            ) : null}
            {found?.towns.length ? (
              <ResultGroup title="Towns and cities">
                {found.towns.map((t) => (
                  <ResultRow
                    key={t.ref}
                    icon="city"
                    title={t.name}
                    meta={[t.admin1_name, t.country_name].filter(Boolean).join(", ")}
                    selected={choice?.kind === "town" && choice.town.ref === t.ref}
                    onPress={() => pick({ kind: "town", town: t })}
                  />
                ))}
              </ResultGroup>
            ) : null}
            {nothingFound ? (
              <View style={styles.gap}>
                <Text style={styles.muted}>Nothing in the imported data matches “{q}”.</Text>
                {wider === undefined ? (
                  <Button
                    label="Search more widely"
                    variant="secondary"
                    icon="search"
                    hint="Asks an OpenStreetMap search service through the Detour server"
                    onPress={() => void searchWider()}
                  />
                ) : wider === "none" ? (
                  <Text style={styles.muted}>
                    The wider search found nothing either. Try the address, or drop a pin.
                  </Text>
                ) : (
                  <ResultGroup title="Other places (OpenStreetMap, via Photon)">
                    {wider.map((p, n) => (
                      <ResultRow
                        key={`${p.ref ?? n}`}
                        icon="pin"
                        title={p.name}
                        meta={[p.city, p.state, p.country].filter(Boolean).join(", ")}
                        selected={choice?.kind === "external" && choice.place === p}
                        onPress={() => pick({ kind: "external", place: p })}
                      />
                    ))}
                  </ResultGroup>
                )}
              </View>
            ) : null}
          </View>
        ) : mode === "address" ? (
          <View style={styles.gap}>
            <Field
              label="Street address"
              value={address}
              onChangeText={(t) => {
                setAddress(t);
                setAddressResults(null);
                setChoice(null);
                clearSuggestions();
              }}
              autoCorrect={false}
              hint="A street and number, a postcode or a known place. Found through an OpenStreetMap search service, via the Detour server."
            />
            <Button
              label="Find the address"
              icon="search"
              variant="secondary"
              testID="find-address"
              disabled={address.trim().length < MIN_QUERY || working !== null}
              loading={working === "address"}
              onPress={() => void findAddress()}
            />
            {searchError ? <Notice tone="error">{searchError}</Notice> : null}
            {addressResults === "none" ? (
              <Text style={styles.muted}>
                No address matches “{address.trim()}”. Check the spelling, or drop a pin.
              </Text>
            ) : addressResults ? (
              <ResultGroup title="Addresses (OpenStreetMap, via Photon)">
                {addressResults.map((p, n) => (
                  <ResultRow
                    key={`${p.ref ?? n}`}
                    icon="pin"
                    title={p.name}
                    meta={externalAddress(p)}
                    selected={choice?.kind === "external" && choice.place === p}
                    onPress={() => pick({ kind: "external", place: p })}
                  />
                ))}
              </ResultGroup>
            ) : null}
            {choice?.kind === "external" ? (
              <Field
                label="Name of the place"
                value={customName}
                onChangeText={(t) => {
                  setCustomName(t);
                  setSavedId(null);
                  clearSuggestions();
                }}
                hint="Your own name for it, for example “Friend's flat”."
              />
            ) : null}
          </View>
        ) : (
          <View style={styles.gap}>
            <Text style={styles.muted}>Tap the map where the place is, then name it.</Text>
            {mapConfig && centre ? (
              <View style={styles.map}>
                <Map
                  style={styles.fill}
                  mapStyle={mapConfig.style_url}
                  logo={false}
                  attribution={false}
                  onPress={(e) => {
                    const [lon, lat] = e.nativeEvent.lngLat;
                    const name = customName;
                    pick({ kind: "pin", lat, lon });
                    setCustomName(name);
                  }}
                >
                  <Camera initialViewState={{ center: [centre.lon, centre.lat], zoom: 12 }} />
                  {choice?.kind === "pin" ? (
                    <Marker id="pin" lngLat={[choice.lon, choice.lat]} anchor="bottom">
                      <View
                        style={styles.pin}
                        accessible
                        accessibilityLabel="The pin you dropped"
                      />
                    </Marker>
                  ) : null}
                </Map>
                <AttributionBar lines={mapConfig.attribution} userInteractionCount={0} />
              </View>
            ) : (
              <Notice tone="warning">The map needs a connection to the server.</Notice>
            )}
            {choice?.kind === "pin" ? (
              <Text style={styles.muted}>
                Pin at {choice.lat.toFixed(5)}, {choice.lon.toFixed(5)}
              </Text>
            ) : null}
            <Field
              label="Name of the place"
              value={customName}
              onChangeText={(t) => {
                setCustomName(t);
                setSavedId(null);
                clearSuggestions();
              }}
              hint="Your own name for it, for example “Friend's flat”."
            />
          </View>
        )}

        {choice ? (
          <View style={styles.gap}>
            <Text style={styles.label}>
              How long to stay at {choiceName(choice, customName) || "it"}
            </Text>
            <View style={styles.row}>
              {choice.kind === "sight" ? (
                <Chip
                  label="Typical length"
                  selected={minutes === null}
                  onPress={() => {
                    setMinutes(null);
                    clearSuggestions();
                  }}
                />
              ) : null}
              {DURATIONS.map((m) => (
                <Chip
                  key={m}
                  label={formatMinutes(m)}
                  selected={minutes === m}
                  onPress={() => {
                    setMinutes(m);
                    clearSuggestions();
                  }}
                />
              ))}
            </View>
            {!isManual ? (
              <View style={styles.row}>
                <Chip
                  label="Suggest a day"
                  selected={!choosing}
                  testID="how-suggest"
                  onPress={() => setHow("suggest")}
                />
                <Chip
                  label="Choose day and time"
                  selected={choosing}
                  testID="how-choose"
                  onPress={() => setHow("choose")}
                />
              </View>
            ) : (
              <Text style={styles.muted}>
                This trip has no proposed plan yet, so pick the day and time yourself.
              </Text>
            )}
            {choosing ? (
              itinerary.data ? (
                <ChooseSlot
                  days={itinerary.data.days}
                  startDate={trip?.start_date ?? null}
                  minutes={minutes ?? 60}
                  name={choiceName(choice, customName)}
                  working={working === "preview"}
                  disabled={!ready}
                  onSubmit={(slot) => void addAt(slot)}
                />
              ) : (
                <Text style={styles.muted}>Reading the plan…</Text>
              )
            ) : !suggestions ? (
              <Button
                label="Find the best day"
                icon="calendar"
                testID="find-days"
                fill
                disabled={!ready}
                loading={working === "find"}
                hint="Detour tries each day and suggests up to three, with what would change"
                onPress={() => void find()}
              />
            ) : null}
          </View>
        ) : null}

        {problem ? (
          <View style={styles.gap}>
            <Notice tone="error">{problem.message}</Notice>
            {problem.issues.map((i) => (
              <Text key={i} style={styles.issue}>
                • {i}
              </Text>
            ))}
          </View>
        ) : null}

        {suggestions && !choosing ? (
          <Suggestions
            suggestions={suggestions}
            picked={picked}
            onPick={setPicked}
            working={working === "preview"}
            onPreview={() => void preview()}
          />
        ) : null}

        {!changes.connected ? (
          <Text style={styles.muted}>Adding a place needs a connection to the server.</Text>
        ) : null}
      </View>
    </ScrollView>
  );
}

function Suggestions({
  suggestions,
  picked,
  onPick,
  working,
  onPreview,
}: {
  suggestions: PlaceSuggestions;
  picked: number | null;
  onPick: (n: number) => void;
  working: boolean;
  onPreview: () => void;
}) {
  if (suggestions.suggestions.length === 0) {
    return (
      <View style={styles.gap} testID="place-suggestions">
        <Notice tone="warning" label="No day fits">
          {suggestions.issues.map((i) => i.text).join(" ") ||
            `None of the ${suggestions.days_considered} days can take ${suggestions.name}.`}
        </Notice>
      </View>
    );
  }
  const count = suggestions.suggestions.length;
  return (
    <View style={styles.gap} testID="place-suggestions">
      <Text style={styles.heading} accessibilityRole="header">
        {count === 1 ? "The day that fits" : `The ${count} best days`} for {suggestions.name}
      </Text>
      <Text style={styles.muted}>
        {formatMinutes(suggestions.duration_minutes)}{" "}
        {suggestions.duration_source === "user" ? "(set by you)" : "(typical visit length)"} ·{" "}
        {suggestions.days_considered} days tried. Travel times are from the cache or labelled
        estimates; the preview checks them.
      </Text>
      {suggestions.suggestions.map((s, n) => (
        <SuggestionCard
          key={s.day}
          rank={s.rank}
          title={placeSuggestionTitle(s)}
          where={placeSuggestionWhere(s)}
          impact={travelImpact(s.travel_minutes_added, s.estimated)}
          affected={affectedLines(s.diff)}
          reasons={s.reasons.map((r) => r.text)}
          selected={picked === n}
          onPress={() => onPick(n)}
          accessibilityLabel={placeSuggestionSentence(s)}
          testID={`suggestion-day-${s.day}`}
        />
      ))}
      <Button
        label="Preview this change"
        testID="preview-change"
        fill
        disabled={picked === null}
        loading={working}
        hint="Shows everything that would change. Nothing changes until you accept."
        onPress={onPreview}
      />
    </View>
  );
}

function ResultGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={styles.gap}>
      <Text style={styles.label} accessibilityRole="header">
        {title}
      </Text>
      {children}
    </View>
  );
}

function ResultRow({
  icon,
  title,
  meta,
  selected,
  onPress,
  hint,
}: {
  icon: IconName;
  title: string;
  meta: string;
  selected: boolean;
  onPress: () => void;
  hint?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}${meta ? `, ${meta}` : ""}`}
      accessibilityHint={hint}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.result, selected && styles.resultSelected]}
    >
      <View style={styles.resultIcon}>
        <Icon name={icon} size={18} color={colors.primary} />
      </View>
      <View style={styles.resultText}>
        <Text style={styles.resultTitle}>
          {selected ? "✓ " : ""}
          {title}
        </Text>
        {meta ? <Text style={styles.muted}>{meta}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl },
  fill: { flex: 1 },
  section: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  body: { padding: spacing.lg, gap: spacing.lg },
  lead: { ...type.body, color: colors.text },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  gap: { gap: spacing.sm },
  heading: { ...type.heading, color: colors.text },
  label: { ...type.small, fontWeight: "700", color: colors.text },
  muted: { ...type.small, color: colors.muted },
  issue: { ...type.small, color: colors.text },
  result: {
    minHeight: TOUCH + 8,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  resultSelected: { backgroundColor: colors.surfaceMuted },
  resultIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.primarySoft,
  },
  resultText: { flex: 1, gap: spacing.xxs },
  resultTitle: { ...type.body, fontWeight: "700", color: colors.text },
  map: {
    height: 280,
    borderRadius: radius.md,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.border,
  },
  pin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.accent,
    borderWidth: 3,
    borderColor: colors.onPrimary,
  },
});
