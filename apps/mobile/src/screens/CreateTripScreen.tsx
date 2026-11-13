import type { DestinationResult, Trip } from "@detour/shared";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError, isOfflineError, planningIssues } from "../api/unwrap";
import { Button } from "../components/Button";
import { Card, Field, Notice, ScreenHeader, Stepper } from "../components/ui";
import { useTripActions } from "../data/actions";
import { useNavigation } from "../nav/Navigator";
import { TOUCH, colors, radius, spacing, type } from "../theme";
import { isValidIsoDate, pluralise } from "../util/format";

export const SEARCH_DEBOUNCE_MS = 350;
export const MIN_QUERY_LENGTH = 2;
export const MAX_DAYS = 30;

type SearchState =
  | { phase: "idle" }
  | { phase: "searching" }
  | { phase: "done"; results: DestinationResult[] }
  | { phase: "error"; offline: boolean; message: string };

/** Why a result cannot be chosen, or null when it can. */
export function unavailableReason(r: DestinationResult): string | null {
  if (r.kind === "area") return "Whole areas cannot be planned yet. Choose a city.";
  if (!r.planning_available) return "Not available yet: this region's data has not been imported.";
  return null;
}

function describeResult(r: DestinationResult): string {
  return [r.admin1_name, r.country_name].filter(Boolean).join(", ");
}

/** "12,5" and "12.50" both mean twelve and a half. Returns null for anything else. */
export function parseBudget(text: string): string | null {
  const t = text.trim().replace(",", ".");
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(t)) return null;
  return t;
}

export type FormErrors = { date?: string; currency?: string; budget?: string };

export function validateForm(values: {
  startDate: string;
  currency: string;
  budget: string;
}): FormErrors {
  const errors: FormErrors = {};
  if (values.startDate.trim() && !isValidIsoDate(values.startDate.trim())) {
    errors.date = "Use the form YYYY-MM-DD, for example 2027-05-01.";
  }
  if (values.currency.trim() && !/^[A-Za-z]{3}$/.test(values.currency.trim())) {
    errors.currency = "Use a three-letter code such as EUR or JPY.";
  }
  if (values.budget.trim() && parseBudget(values.budget) === null) {
    errors.budget = "Use a number such as 25 or 25.50.";
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
  const [days, setDays] = useState(3);
  const [startDate, setStartDate] = useState("");
  const [currency, setCurrency] = useState("");
  const [budget, setBudget] = useState("");
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [working, setWorking] = useState<"creating" | "planning" | null>(null);
  const [problem, setProblem] = useState<{ message: string; issues: string[] } | null>(null);
  const [created, setCreated] = useState<Trip | null>(null);

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

  const errors = validateForm({ startDate, currency, budget });
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

  const submit = async () => {
    setSubmitted(true);
    setProblem(null);
    if (!chosen || hasErrors) return;
    let trip = created;
    if (!trip) {
      setWorking("creating");
      try {
        trip = await actions.createTrip({
          title: name.trim() || `${chosen.name}, ${pluralise(days, "day")}`,
          destination_kind: chosen.kind,
          destination_ref: chosen.ref,
          duration_days: days,
          start_date: startDate.trim() || null,
          currency_code: currency.trim() ? currency.trim().toUpperCase() : null,
          meal_budget_per_person: budget.trim() ? parseBudget(budget) : null,
        });
        setCreated(trip);
      } catch (e) {
        setProblem({ message: describeError(e), issues: [] });
        setWorking(null);
        return;
      }
    }
    await planNow(trip);
  };

  const offline = !actions.connected && state.phase === "error";

  return (
    <View style={styles.fill}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <ScreenHeader title="New trip" onBack={nav.back} />

        {offline ? (
          <Notice tone="warning" label="Offline">
            Planning a trip needs a connection. Your saved trips can still be read.
          </Notice>
        ) : null}

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Where to?</Text>
          {chosen ? (
            <Card accent>
              <Text style={styles.resultName}>{chosen.name}</Text>
              <Text style={styles.resultMeta}>{describeResult(chosen) || "City"}</Text>
              <Button
                label="Change destination"
                variant="secondary"
                onPress={() => {
                  setChosen(null);
                  setCreated(null);
                }}
              />
            </Card>
          ) : (
            <>
              <Field
                label="Destination"
                testID="destination-input"
                hint="A city in one of the imported regions, for example Vienna or Prague."
                value={query}
                onChangeText={setQuery}
                autoCorrect={false}
                autoCapitalize="words"
                returnKeyType="search"
              />
              <SearchResults search={search} waking={waking} query={q} onChoose={setChosen} />
            </>
          )}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Details</Text>
          <Stepper
            label="Days"
            value={days}
            min={1}
            max={MAX_DAYS}
            onChange={setDays}
            unit={(n) => pluralise(n, "day")}
          />
          <Field
            label="Start date (optional)"
            hint="Day dates follow it. Format YYYY-MM-DD."
            value={startDate}
            onChangeText={setStartDate}
            keyboardType="numbers-and-punctuation"
            autoCorrect={false}
            maxLength={10}
            error={submitted || startDate.length === 10 ? (errors.date ?? null) : null}
          />
          <Field
            label="Currency (optional)"
            hint="A three-letter code. Left empty, the destination country's currency is used."
            value={currency}
            onChangeText={(t) => setCurrency(t.toUpperCase())}
            autoCapitalize="characters"
            autoCorrect={false}
            maxLength={3}
            error={submitted || currency.length === 3 ? (errors.currency ?? null) : null}
          />
          <Field
            label="Meal budget per person (optional)"
            hint="For one meal, in the trip currency. It is kept with the trip."
            value={budget}
            onChangeText={setBudget}
            keyboardType="decimal-pad"
            error={submitted ? (errors.budget ?? null) : null}
          />
          <Field
            label="Trip name (optional)"
            hint={chosen ? `Left empty: "${chosen.name}, ${pluralise(days, "day")}".` : undefined}
            value={name}
            onChangeText={setName}
            maxLength={120}
          />
        </View>

        {problem ? (
          <Notice tone="error">
            {problem.message}
            {problem.issues.length > 0 ? ` ${problem.issues.join(" ")}` : ""}
            {created ? " The trip was saved; you can plan it again." : ""}
          </Notice>
        ) : null}
        {working === "planning" ? (
          <Notice tone="info" label="Planning">
            Choosing places and working out travel times. This usually takes a few seconds.
          </Notice>
        ) : null}

        <View style={styles.section}>
          <Button
            testID="plan-trip"
            label={created ? "Try planning again" : "Plan trip"}
            fill
            loading={working !== null}
            disabled={!chosen || offline}
            hint={chosen ? undefined : "Choose a destination first"}
            onPress={() => void submit()}
          />
          {created && problem ? (
            <Button
              label="Open the trip without a plan"
              variant="quiet"
              onPress={() => nav.replace({ name: "trip", tripId: created.id })}
            />
          ) : null}
        </View>
      </ScrollView>
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

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { paddingBottom: spacing.xxl },
  section: { paddingHorizontal: spacing.lg, gap: spacing.md, marginBottom: spacing.lg },
  sectionTitle: { ...type.heading, color: colors.text },
  hint: { ...type.small, color: colors.muted },
  results: { gap: spacing.sm },
  result: {
    minHeight: TOUCH + 8,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: 2,
  },
  resultDisabled: { backgroundColor: colors.surfaceMuted },
  pressed: { opacity: 0.85 },
  resultName: { ...type.heading, color: colors.text },
  resultMeta: { ...type.small, color: colors.muted },
  reason: { ...type.small, color: colors.errorText, fontWeight: "600" },
});
