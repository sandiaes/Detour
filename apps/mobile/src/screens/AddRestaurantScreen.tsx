import type {
  ExternalRestaurant,
  Itinerary,
  RestaurantResult,
  RestaurantSearchResponse,
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
import { ChooseSlot, type ChosenSlot } from "../components/ChooseSlot";
import { Chip, Field, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import {
  MEALS,
  MEAL_LABEL,
  type Meal,
  formatMealTypes,
  parseCoordinate,
  parseCuisines,
  restaurantMeta,
} from "../domain/restaurants";
import { type Route, useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { formatCuisines } from "../util/format";

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
  const itinerary = useResource<Itinerary>(keys.itinerary(route.itineraryId), (c) =>
    call(
      c.GET("/v1/itineraries/{itinerary_id}", {
        params: { path: { itinerary_id: route.itineraryId } },
      }),
    ),
  );
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
  const [working, setWorking] = useState<"preview" | null>(null);
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

  const reset = () => setProblem(null);

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
  const reference = async (): Promise<{ place_id?: string; user_place_id?: string }> => {
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

  /** Adds the restaurant at the day, meal and time the user picked, with no proposal. */
  const addAt = async (slot: ChosenSlot) => {
    setWorking("preview");
    setProblem(null);
    try {
      const ref = await reference();
      await changes.addItem(route.tripId, route.itineraryId, slot.day, {
        type: "meal",
        meal_type: slot.meal ?? "lunch",
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
          Find a restaurant or enter it yourself, then choose its day and time. Opening hours are
          not checked.
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

      {choice ? (
        <View style={styles.section}>
          {itinerary.data ? (
            <ChooseSlot
              days={itinerary.data.days}
              startDate={trip?.start_date ?? null}
              meal
              minutes={null}
              name={choiceName(choice, form)}
              working={working === "preview"}
              disabled={!ready}
              onSubmit={(slot) => void addAt(slot)}
            />
          ) : (
            <Text style={styles.muted}>Reading the plan…</Text>
          )}
          {!changes.connected ? (
            <Text style={styles.muted}>Adding a restaurant needs a connection to the server.</Text>
          ) : null}
        </View>
      ) : null}
    </ScrollView>
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
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  resultSelected: { backgroundColor: colors.surfaceMuted },
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
