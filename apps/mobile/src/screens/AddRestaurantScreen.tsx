import type {
  ExternalRestaurant,
  RestaurantResult,
  RestaurantSearchResponse,
  SlotRequest,
  SlotSuggestion,
  SlotSuggestions,
  Trip,
  UserPlace,
} from "@detour/shared";
import { Camera, Map, Marker } from "@maplibre/maplibre-react-native";
import { type ReactNode, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError, planningIssues } from "../api/unwrap";
import { AttributionBar } from "../components/AttributionBar";
import { Button } from "../components/Button";
import { Chip, Field, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import {
  MEALS,
  MEAL_LABEL,
  type Meal,
  detourText,
  formatMealTypes,
  parseCoordinate,
  parseCuisines,
  restaurantMeta,
  suggestionPlace,
  suggestionTitle,
} from "../domain/restaurants";
import { type Route, useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { formatClock, formatCuisines } from "../util/format";
import {
  type AffectedLine,
  SuggestionCard as DsSuggestionCard,
} from "../components/ds/SuggestionCard";

type AddRoute = Extract<Route, { name: "addRestaurant" }>;

export const RESTAURANT_DEBOUNCE_MS = 350;
const MIN_QUERY = 2;
/** Restaurants are searched within this distance of the trip's destination. */
export const RESTAURANT_RADIUS_M = 50_000;

/** What the user picked: an imported place to eat, one saved earlier, an external search result,
 * or a restaurant entered by hand. */
export type Choice =
  | { kind: "imported"; place: RestaurantResult }
  | { kind: "saved"; place: UserPlace }
  | { kind: "external"; place: ExternalRestaurant }
  | { kind: "hand" };

type Form = {
  name: string;
  cuisines: string;
  meals: Meal[];
  lat: string;
  lon: string;
};

const EMPTY_FORM: Form = { name: "", cuisines: "", meals: [], lat: "", lon: "" };

/** The name the choice goes by. */
function choiceName(c: Choice, form: Form): string {
  switch (c.kind) {
    case "imported":
      return c.place.name ?? "this place";
    case "saved":
    case "external":
      return c.place.name;
    case "hand":
      return form.name.trim();
  }
}

export function AddRestaurantScreen({ route }: { route: AddRoute }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const changes = useChangeActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === route.tripId);
  const client = state.phase === "ready" ? state.connection.client : null;
  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;
  const centre = trip?.destination;

  const [mode, setMode] = useState<"search" | "hand">("search");
  const [query, setQuery] = useState(route.preset?.name ?? "");
  const [results, setResults] = useState<Record<string, RestaurantSearchResponse>>({});
  const [wide, setWide] = useState<Record<string, RestaurantSearchResponse>>({});
  const [searchError, setSearchError] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(
    route.preset ? { kind: "imported", place: route.preset } : null,
  );
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  // The user place made for an external or hand-entered restaurant, so retrying does not save it
  // twice.
  const [savedId, setSavedId] = useState<string | null>(null);
  const [slots, setSlots] = useState<SlotSuggestions | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [working, setWorking] = useState<"find" | "preview" | null>(null);
  const [problem, setProblem] = useState<{ message: string; issues: string[] } | null>(null);

  const q = query.trim();
  const key = q.toLowerCase();
  const needsSearch = mode === "search" && q.length >= MIN_QUERY && results[key] === undefined;
  useEffect(() => {
    if (!needsSearch || !client || !centre) return;
    let current = true;
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const found = await call(
            client.GET("/v1/restaurants/search", {
              params: {
                query: {
                  q,
                  lat: centre.lat,
                  lon: centre.lon,
                  radius_m: RESTAURANT_RADIUS_M,
                  limit: 8,
                },
              },
            }),
          );
          if (!current) return;
          setSearchError(null);
          setResults((r) => ({ ...r, [key]: found }));
        } catch (e) {
          if (current) setSearchError(describeError(e));
        }
      })();
    }, RESTAURANT_DEBOUNCE_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [needsSearch, client, centre, q, key]);

  const searchWider = async () => {
    if (!client || !centre) return;
    try {
      const found = await call(
        client.GET("/v1/restaurants/search", {
          params: {
            query: { q, lat: centre.lat, lon: centre.lon, limit: 8, include_external: true },
          },
        }),
      );
      setWide((w) => ({ ...w, [key]: found }));
    } catch (e) {
      setSearchError(describeError(e));
    }
  };

  const reset = () => {
    setSlots(null);
    setPicked(null);
    setProblem(null);
  };

  const pick = (c: Choice) => {
    setChoice(c);
    setSavedId(null);
    reset();
    if (c.kind === "external") {
      // The venue rule's meals are the starting point; the user can change them.
      setForm({
        ...EMPTY_FORM,
        name: c.place.name,
        meals: MEALS.filter((m) => c.place.meal_types.includes(m)),
        lat: String(c.place.lat),
        lon: String(c.place.lon),
      });
    }
  };

  const edit = (patch: Partial<Form>) => {
    setForm((f) => ({ ...f, ...patch }));
    reset();
  };

  const toggleMeal = (meal: Meal) =>
    edit({
      meals: form.meals.includes(meal)
        ? form.meals.filter((m) => m !== meal)
        : [...form.meals, meal],
    });

  // Entered by hand or found outside: the user's own place, with what they typed.
  const editable = choice?.kind === "hand" || choice?.kind === "external";
  const lat = parseCoordinate(form.lat, "lat");
  const lon = parseCoordinate(form.lon, "lon");
  const handReady = form.name.trim().length > 0 && lat !== null && lon !== null;
  const ready = choice !== null && (!editable || handReady) && !working;

  /** The place reference the server wants; saves the user's own place first when needed. */
  const reference = async (): Promise<Pick<SlotRequest, "place_id" | "user_place_id">> => {
    if (!choice) throw new Error("nothing chosen");
    if (choice.kind === "imported") return { place_id: choice.place.id };
    if (choice.kind === "saved") return { user_place_id: choice.place.id };
    if (lat === null || lon === null) throw new Error("no location");
    const fields = {
      name: form.name.trim(),
      lat,
      lon,
      cuisines: parseCuisines(form.cuisines) ?? null,
      meal_types: form.meals.length ? form.meals : null,
    };
    if (savedId) {
      const updated = await changes.updatePlace(savedId, fields);
      return { user_place_id: updated.id };
    }
    const { cuisines, meal_types, ...rest } = fields;
    const place = await changes.savePlace({
      kind: "restaurant",
      ...rest,
      ...(cuisines ? { cuisines } : {}),
      ...(meal_types ? { meal_types } : {}),
      ...(choice.kind === "external" && choice.place.ref
        ? {
            source: "search_result" as const,
            search_provider: "photon" as const,
            search_ref: choice.place.ref,
          }
        : { source: "manual_pin" as const }),
    });
    setSavedId(place.id);
    return { user_place_id: place.id };
  };

  const find = async () => {
    setWorking("find");
    reset();
    try {
      const ref = await reference();
      const found = await changes.suggestSlots(route.itineraryId, ref);
      setSlots(found);
      setPicked(found.suggestions.length ? 0 : null);
    } catch (e) {
      setProblem({ message: describeError(e), issues: planningIssues(e) });
    } finally {
      setWorking(null);
    }
  };

  const preview = async () => {
    if (!slots || picked === null) return;
    const slot = slots.suggestions[picked];
    if (!slot) return;
    setWorking("preview");
    setProblem(null);
    try {
      const ref = await reference();
      const change = await changes.preview(route.itineraryId, {
        action: "add_restaurant",
        ...ref,
        day: slot.day,
        meal_type: slot.meal_type,
        after_item_id: slot.after_item_id,
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

  const found = results[key];
  const wider = wide[key];
  const widerResults = wider?.external.results ?? [];
  const nothingFound =
    found !== undefined && found.results.length === 0 && found.your_places.length === 0;

  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <ScreenHeader
        title="Add a restaurant"
        subtitle={trip ? `${trip.title} · ${trip.destination.name}` : undefined}
        onBack={nav.back}
      />
      <View style={styles.section}>
        <Text style={styles.lead}>
          Find a restaurant or enter it yourself. Detour then suggests the best day and meal for it,
          and shows what would change before anything changes. Opening hours are not checked.
        </Text>
        <View style={styles.row}>
          <Chip
            label="Search"
            selected={mode === "search"}
            onPress={() => {
              setMode("search");
              setChoice(null);
              reset();
            }}
          />
          <Chip
            label="Enter by hand"
            selected={mode === "hand"}
            testID="hand-mode"
            onPress={() => {
              setMode("hand");
              setChoice({ kind: "hand" });
              setSavedId(null);
              setForm(EMPTY_FORM);
              reset();
            }}
          />
        </View>
      </View>

      {mode === "search" ? (
        <View style={styles.section}>
          <Field
            label="Restaurant name"
            value={query}
            onChangeText={(t) => {
              setQuery(t);
              setChoice(null);
              reset();
            }}
            autoCorrect={false}
            hint="At least two letters. The map data is searched first."
          />
          {searchError ? <Notice tone="error">{searchError}</Notice> : null}
          {q.length >= MIN_QUERY && found === undefined && !searchError ? (
            <Text style={styles.muted}>Searching…</Text>
          ) : null}
          {found?.results.length ? (
            <ResultGroup title="Restaurants in the map data">
              {found.results.map((p) => (
                <ResultRow
                  key={p.id}
                  title={p.name ?? "Unnamed place"}
                  meta={restaurantMeta(p)}
                  selected={choice?.kind === "imported" && choice.place.id === p.id}
                  onPress={() => pick({ kind: "imported", place: p })}
                />
              ))}
            </ResultGroup>
          ) : null}
          {found?.your_places.length ? (
            <ResultGroup title="Saved by you">
              {found.your_places.map((p) => (
                <ResultRow
                  key={p.id}
                  title={p.name}
                  meta={`${formatCuisines(p.cuisines)} · ${formatMealTypes(p.meal_types)}`}
                  selected={choice?.kind === "saved" && choice.place.id === p.id}
                  onPress={() => pick({ kind: "saved", place: p })}
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
                  hint="Asks an OpenStreetMap search service through the Detour server"
                  onPress={() => void searchWider()}
                />
              ) : widerResults.length === 0 ? (
                <Text style={styles.muted}>
                  {wider.external.state === "ok" || wider.external.state === "cached"
                    ? "The wider search found no restaurant either."
                    : "The wider search is not available right now."}{" "}
                  You can enter the restaurant by hand.
                </Text>
              ) : (
                <ResultGroup title="Other restaurants (OpenStreetMap, via Photon)">
                  {widerResults.map((p, n) => (
                    <ResultRow
                      key={`${p.ref ?? n}`}
                      title={p.name}
                      meta={[
                        "Cuisine not specified",
                        p.venue_type === "cafe" ? "Café" : "Restaurant",
                        p.city,
                        p.country,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                      selected={choice?.kind === "external" && choice.place === p}
                      onPress={() => pick({ kind: "external", place: p })}
                    />
                  ))}
                </ResultGroup>
              )}
              <Button
                label="Enter it by hand"
                variant="secondary"
                onPress={() => {
                  setMode("hand");
                  setChoice({ kind: "hand" });
                  setForm({ ...EMPTY_FORM, name: q });
                }}
              />
            </View>
          ) : null}
        </View>
      ) : null}

      {editable ? (
        <View style={styles.section}>
          <Field
            label="Name of the restaurant"
            value={form.name}
            onChangeText={(t) => edit({ name: t })}
          />
          <Field
            label="Cuisine (optional)"
            value={form.cuisines}
            onChangeText={(t) => edit({ cuisines: t })}
            autoCorrect={false}
            hint="For example “italian, pizza”. Left empty it stays “Cuisine not specified”."
          />
          <Text style={styles.label}>Meals it serves (optional)</Text>
          <View style={styles.row}>
            {MEALS.map((m) => (
              <Chip
                key={m}
                label={MEAL_LABEL[m]}
                selected={form.meals.includes(m)}
                onPress={() => toggleMeal(m)}
              />
            ))}
          </View>
          {form.meals.length === 0 ? (
            <Text style={styles.muted}>
              None chosen: the meals it serves are not specified, so it is judged by place and
              timing alone.
            </Text>
          ) : null}
          <Text style={styles.label}>Where it is</Text>
          <Text style={styles.muted}>Tap the map, or type the coordinates.</Text>
          {mapConfig && centre ? (
            <View style={styles.map}>
              <Map
                style={styles.fill}
                mapStyle={mapConfig.style_url}
                logo={false}
                attribution={false}
                onPress={(e) => {
                  const [lonTapped, latTapped] = e.nativeEvent.lngLat;
                  edit({ lat: latTapped.toFixed(6), lon: lonTapped.toFixed(6) });
                }}
              >
                <Camera
                  initialViewState={{
                    center: [lon ?? centre.lon, lat ?? centre.lat],
                    zoom: 12,
                  }}
                />
                {lat !== null && lon !== null ? (
                  <Marker id="pin" lngLat={[lon, lat]} anchor="bottom">
                    <View style={styles.pin} accessible accessibilityLabel="The restaurant's pin" />
                  </Marker>
                ) : null}
              </Map>
              <AttributionBar lines={mapConfig.attribution} userInteractionCount={0} />
            </View>
          ) : (
            <Notice tone="warning">The map needs a connection to the server.</Notice>
          )}
          <View style={styles.row}>
            <View style={styles.half}>
              <Field
                label="Latitude"
                value={form.lat}
                onChangeText={(t) => edit({ lat: t })}
                keyboardType="numbers-and-punctuation"
                error={form.lat && lat === null ? "A number from −90 to 90" : null}
              />
            </View>
            <View style={styles.half}>
              <Field
                label="Longitude"
                value={form.lon}
                onChangeText={(t) => edit({ lon: t })}
                keyboardType="numbers-and-punctuation"
                error={form.lon && lon === null ? "A number from −180 to 180" : null}
              />
            </View>
          </View>
        </View>
      ) : null}

      {problem ? (
        <View style={styles.section}>
          <Notice tone="error">{problem.message}</Notice>
          {problem.issues.map((i) => (
            <Text key={i} style={styles.issue}>
              • {i}
            </Text>
          ))}
        </View>
      ) : null}

      {slots === null ? (
        <View style={styles.section}>
          <Button
            label="Find the best day and meal"
            testID="find-slots"
            fill
            disabled={!ready}
            loading={working === "find"}
            hint="Suggests up to three places in the plan. Nothing changes yet."
            onPress={() => void find()}
          />
          {choice && !editable ? (
            <Text style={styles.muted}>Chosen: {choiceName(choice, form)}</Text>
          ) : null}
          {!changes.connected ? (
            <Text style={styles.muted}>Adding a restaurant needs a connection to the server.</Text>
          ) : null}
        </View>
      ) : (
        <Suggestions
          slots={slots}
          picked={picked}
          onPick={setPicked}
          working={working === "preview"}
          onPreview={() => void preview()}
        />
      )}
    </ScrollView>
  );
}

function Suggestions({
  slots,
  picked,
  onPick,
  working,
  onPreview,
}: {
  slots: SlotSuggestions;
  picked: number | null;
  onPick: (n: number) => void;
  working: boolean;
  onPreview: () => void;
}) {
  if (slots.suggestions.length === 0) {
    return (
      <View style={styles.section}>
        <Notice tone="warning">
          {slots.issues.map((i) => i.text).join(" ") || "No slot fits this restaurant."}
        </Notice>
      </View>
    );
  }
  return (
    <View style={styles.section} testID="slot-suggestions">
      <Text style={styles.heading} accessibilityRole="header">
        Best places in the plan for {slots.restaurant.name}
      </Text>
      <Text style={styles.muted}>
        {formatCuisines(slots.restaurant.cuisines)} · {formatMealTypes(slots.restaurant.meal_types)}
      </Text>
      {slots.suggestions.map((s, n) => (
        <SuggestionCard
          key={`${s.day}-${s.meal_type}`}
          slot={s}
          selected={picked === n}
          onPress={() => onPick(n)}
        />
      ))}
      <Button
        label="Preview this change"
        testID="preview-slot"
        fill
        disabled={picked === null}
        loading={working}
        hint="Shows what would change. Nothing changes until you accept."
        onPress={onPreview}
      />
    </View>
  );
}

function SuggestionCard({
  slot,
  selected,
  onPress,
}: {
  slot: SlotSuggestion;
  selected: boolean;
  onPress: () => void;
}) {
  const affected: AffectedLine[] = [
    ...(slot.replaces
      ? [{ tone: "info" as const, text: `Replaces ${slot.replaces}, planned for this meal` }]
      : []),
    ...slot.items_moved.map((m) => ({
      tone: "info" as const,
      text: `${m.name}: ${formatClock(m.old_start_time) ?? m.old_start_time} → ${formatClock(m.new_start_time) ?? m.new_start_time}`,
    })),
  ];
  return (
    <DsSuggestionCard
      rank={slot.rank}
      title={suggestionTitle(slot)}
      where={suggestionPlace(slot)}
      impact={detourText(slot)}
      affected={affected}
      reasons={slot.reasons.map((r) => r.text)}
      selected={selected}
      onPress={onPress}
      accessibilityLabel={`${slot.rank === 1 ? "Best: " : "Alternative: "}${suggestionTitle(slot)}`}
    />
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
  title,
  meta,
  selected,
  onPress,
}: {
  title: string;
  meta: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}${meta ? `, ${meta}` : ""}`}
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.result, selected && styles.resultSelected]}
    >
      <Text style={styles.resultTitle}>
        {selected ? "✓ " : ""}
        {title}
      </Text>
      {meta ? <Text style={styles.muted}>{meta}</Text> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl },
  fill: { flex: 1 },
  section: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg, gap: spacing.sm },
  lead: { ...type.body, color: colors.text },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  half: { flex: 1, minWidth: 140 },
  gap: { gap: spacing.sm },
  heading: { ...type.heading, color: colors.text },
  label: { ...type.small, fontWeight: "700", color: colors.text },
  small: { ...type.small, color: colors.text },
  muted: { ...type.small, color: colors.muted },
  issue: { ...type.small, color: colors.text },
  result: {
    minHeight: TOUCH,
    justifyContent: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  resultSelected: { borderColor: colors.primary, borderWidth: 2 },
  resultTitle: { ...type.heading, color: colors.text },
  map: {
    height: 240,
    borderRadius: radius.md,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.border,
  },
  pin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.markerSelected,
    borderWidth: 3,
    borderColor: colors.onPrimary,
  },
});
