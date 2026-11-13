import type {
  ChangeSetCreate,
  DestinationResult,
  ExternalPlace,
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
import { Chip, Field, Notice, ScreenHeader } from "../components/ui";
import { keys } from "../data/actions";
import { useChangeActions } from "../data/changes";
import { useResource } from "../data/DataProvider";
import { type Route, useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { formatMeters, formatMinutes } from "../util/format";

type AddRoute = Extract<Route, { name: "addPlace" }>;

export const SEARCH_DEBOUNCE_MS = 350;
const MIN_QUERY = 2;
/** Sights are searched within this distance of the trip's destination. */
export const SIGHT_RADIUS_M = 50_000;
export const DURATIONS = [30, 60, 90, 120, 180] as const;

/** What the user picked: an imported sight, a town, an external result or a pin. */
export type Choice =
  | { kind: "sight"; place: PlaceSummary }
  | { kind: "town"; town: DestinationResult }
  | { kind: "external"; place: ExternalPlace }
  | { kind: "pin"; lat: number; lon: number };

type Results = { sights: PlaceSummary[]; towns: DestinationResult[]; external: ExternalPlace[] };

function choiceName(c: Choice, pinName: string): string {
  switch (c.kind) {
    case "sight":
      return c.place.name ?? c.place.category;
    case "town":
      return c.town.name;
    case "external":
      return c.place.name;
    case "pin":
      return pinName.trim();
  }
}

/** The change-set body for a choice, saving the place as one of the user's places first when it
 * is not an imported sight. */
export async function bodyFor(
  choice: Choice,
  minutes: number | null,
  pinName: string,
  savePlace: ReturnType<typeof useChangeActions>["savePlace"],
): Promise<ChangeSetCreate> {
  if (choice.kind === "sight") {
    return {
      action: "add_place",
      place_id: choice.place.id,
      ...(minutes ? { duration_minutes: minutes } : {}),
    };
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
            name: choice.place.name,
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
            name: pinName.trim(),
            lat: choice.lat,
            lon: choice.lon,
            source: "manual_pin" as const,
          };
  const place = await savePlace(base);
  return { action: "add_place", user_place_id: place.id, duration_minutes: minutes ?? 60 };
}

export function AddPlaceScreen({ route }: { route: AddRoute }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const changes = useChangeActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const trip = trips.data?.find((t) => t.id === route.tripId);
  const client = state.phase === "ready" ? state.connection.client : null;
  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;

  const [mode, setMode] = useState<"search" | "pin">("search");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Record<string, Results>>({});
  const [wide, setWide] = useState<Record<string, ExternalPlace[] | "none">>({});
  const [searchError, setSearchError] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [pinName, setPinName] = useState("");
  const [minutes, setMinutes] = useState<number | null>(null);
  const [working, setWorking] = useState(false);
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
          const [places, towns] = await Promise.all([
            call(
              client.GET("/v1/places/search", {
                params: {
                  query: {
                    q,
                    kind: "attraction",
                    lat: centre.lat,
                    lon: centre.lon,
                    radius_m: SIGHT_RADIUS_M,
                    limit: 8,
                  },
                },
              }),
            ),
            call(client.GET("/v1/destinations/search", { params: { query: { q, limit: 5 } } })),
          ]);
          if (!current) return;
          setSearchError(null);
          setResults((r) => ({
            ...r,
            [key]: {
              sights: places.results.filter((p) => p.name),
              towns: towns.results.filter((t) => t.kind === "city"),
              external: [],
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

  const searchWider = async () => {
    if (!client || !centre) return;
    try {
      const response = await call(
        client.GET("/v1/places/search", {
          params: {
            query: { q, lat: centre.lat, lon: centre.lon, limit: 8, include_external: true },
          },
        }),
      );
      const external = response.external.results ?? [];
      setWide((w) => ({ ...w, [key]: external.length ? external : "none" }));
    } catch (e) {
      setSearchError(describeError(e));
    }
  };

  const pick = (c: Choice) => {
    setChoice(c);
    setProblem(null);
    // A sight has a typical length; anything else needs one from the user.
    setMinutes(c.kind === "sight" ? null : c.kind === "town" ? 120 : 60);
  };

  const ready = choice !== null && (choice.kind !== "pin" || pinName.trim().length > 0) && !working;

  const submit = async () => {
    if (!choice) return;
    setWorking(true);
    setProblem(null);
    try {
      const body = await bodyFor(choice, minutes, pinName, changes.savePlace);
      const change = await changes.preview(route.itineraryId, body);
      nav.replace({
        name: "changePreview",
        tripId: route.tripId,
        itineraryId: route.itineraryId,
        changeSetId: change.id,
      });
    } catch (e) {
      setProblem({ message: describeError(e), issues: planningIssues(e) });
    } finally {
      setWorking(false);
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
          The place becomes a visit every recalculation keeps. You see what would change before
          anything changes.
        </Text>
        <View style={styles.row}>
          <Chip label="Search" selected={mode === "search"} onPress={() => setMode("search")} />
          <Chip
            label="Drop a pin"
            selected={mode === "pin"}
            testID="pin-mode"
            onPress={() => {
              setMode("pin");
              setChoice(null);
            }}
          />
        </View>
      </View>

      {mode === "search" ? (
        <View style={styles.section}>
          <Field
            label="Sight, town or place"
            value={query}
            onChangeText={(t) => {
              setQuery(t);
              setChoice(null);
            }}
            autoCorrect={false}
            hint="At least two letters. Sights near the trip and towns are searched first."
          />
          {searchError ? <Notice tone="error">{searchError}</Notice> : null}
          {q.length >= MIN_QUERY && found === undefined && !searchError ? (
            <Text style={styles.muted}>Searching…</Text>
          ) : null}
          {found?.sights.length ? (
            <ResultGroup title="Sights in the map data">
              {found.sights.map((p) => (
                <ResultRow
                  key={p.id}
                  title={p.name ?? p.category}
                  meta={[
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
                  hint="Asks an OpenStreetMap search service through the Detour server"
                  onPress={() => void searchWider()}
                />
              ) : wider === "none" ? (
                <Text style={styles.muted}>
                  The wider search found nothing either. Drop a pin instead.
                </Text>
              ) : (
                <ResultGroup title="Other places (OpenStreetMap, via Photon)">
                  {wider.map((p, n) => (
                    <ResultRow
                      key={`${p.ref ?? n}`}
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
      ) : (
        <View style={styles.section}>
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
                  pick({ kind: "pin", lat, lon });
                }}
              >
                <Camera initialViewState={{ center: [centre.lon, centre.lat], zoom: 12 }} />
                {choice?.kind === "pin" ? (
                  <Marker id="pin" lngLat={[choice.lon, choice.lat]} anchor="bottom">
                    <View style={styles.pin} accessible accessibilityLabel="The pin you dropped" />
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
            value={pinName}
            onChangeText={setPinName}
            hint="Your own name for it, for example “Friend's flat”."
          />
        </View>
      )}

      {choice ? (
        <View style={styles.section}>
          <Text style={styles.label}>
            How long to stay at {choiceName(choice, pinName) || "it"}
          </Text>
          <View style={styles.row}>
            {choice.kind === "sight" ? (
              <Chip
                label="Typical length"
                selected={minutes === null}
                onPress={() => setMinutes(null)}
              />
            ) : null}
            {DURATIONS.map((m) => (
              <Chip
                key={m}
                label={formatMinutes(m)}
                selected={minutes === m}
                onPress={() => setMinutes(m)}
              />
            ))}
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

      <View style={styles.section}>
        <Button
          label="Preview the change"
          testID="preview-change"
          fill
          disabled={!ready}
          loading={working}
          hint="Shows what would change. Nothing changes until you accept."
          onPress={() => void submit()}
        />
        {!changes.connected ? (
          <Text style={styles.muted}>Adding a place needs a connection to the server.</Text>
        ) : null}
      </View>
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
  gap: { gap: spacing.sm },
  label: { ...type.small, fontWeight: "700", color: colors.text },
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
    backgroundColor: colors.markerSelected,
    borderWidth: 3,
    borderColor: colors.onPrimary,
  },
});
