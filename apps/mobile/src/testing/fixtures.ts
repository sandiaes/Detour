import type { DestinationResult, Itinerary, ItinerarySummary, Trip } from "@detour/shared";

export const TRIP_ID = "00000000-0000-4000-8000-0000000000a1";
export const ESSENTIALS_ID = "00000000-0000-4000-8000-0000000000e1";
export const WIDER_ID = "00000000-0000-4000-8000-0000000000e2";
const GENERATION = "00000000-0000-4000-8000-0000000000f1";

export function makeTrip(over: Partial<Trip> = {}): Trip {
  return {
    id: TRIP_ID,
    title: "Vienna, 2 days",
    destination: { kind: "city", ref: "900101", name: "Vienna", lat: 48.2082, lon: 16.3738 },
    duration_days: 2,
    start_date: "2027-05-01",
    end_date: "2027-05-02",
    currency_code: "EUR",
    meal_budget_per_person: "25.00",
    price_band_thresholds: null,
    selected_itinerary_id: null,
    status: "active",
    archived_at: null,
    is_seed: false,
    created_at: "2026-11-12T10:00:00Z",
    updated_at: "2026-11-12T10:00:00Z",
    ...over,
  } as Trip;
}

const STATS = {
  essentials: {
    visits: 5,
    days_with_visits: 2,
    visit_minutes: 420,
    travel_minutes: 40,
    travel_seconds: 2400,
    routed_transfers: 1,
    estimated_transfers: 2,
    day_utilisation_permille: 500,
    travel_share_permille: 90,
  },
  wider: {
    visits: 8,
    days_with_visits: 2,
    visit_minutes: 600,
    travel_minutes: 95,
    travel_seconds: 5700,
    routed_transfers: 3,
    estimated_transfers: 4,
    day_utilisation_permille: 750,
    travel_share_permille: 140,
  },
};

export function makeSummary(
  profile: "essentials" | "wider",
  over: Partial<ItinerarySummary> = {},
): ItinerarySummary {
  return {
    id: profile === "essentials" ? ESSENTIALS_ID : WIDER_ID,
    trip_id: TRIP_ID,
    generation_id: GENERATION,
    profile,
    status: "proposed",
    version: 1,
    engine_version: "planner-1.0.0",
    config_version: "test",
    import_run_id: null,
    seed: 0,
    diversity_score: 0.4,
    notes: [],
    stats: STATS[profile],
    created_at: "2026-11-12T10:00:00Z",
    ...over,
  } as ItinerarySummary;
}

type ItemInit = {
  id: string;
  name: string;
  lat: number | null;
  lon: number | null;
  start: string | null;
  end?: string | null;
  minutes: number;
  type?: "visit" | "meal" | "free_time";
  mealType?: "lunch" | null;
  source?: "category_default" | "user";
  reasons?: string[];
  transfer?: {
    to: string;
    mode?: "walk" | "drive";
    seconds: number;
    meters: number;
    confidence: "routed" | "estimated";
  };
};

function item(day: string, position: number, i: ItemInit) {
  return {
    id: i.id,
    day_id: day,
    position,
    type: i.type ?? "visit",
    meal_type: i.mealType ?? null,
    place_id: null,
    user_place_id: null,
    display_name: i.name,
    lat: i.lat,
    lon: i.lon,
    start_time: i.start,
    end_time: i.end ?? null,
    duration_minutes: i.minutes,
    duration_source: i.source ?? "category_default",
    origin: "engine" as const,
    locked: false,
    reasons: (i.reasons ?? []).map((_, n) => `R${n}`),
    reason_texts: i.reasons ?? [],
    transfer: i.transfer
      ? {
          to_item_id: i.transfer.to,
          mode: i.transfer.mode ?? "walk",
          seconds: i.transfer.seconds,
          meters: i.transfer.meters,
          confidence: i.transfer.confidence,
        }
      : null,
  };
}

export function makeItinerary(
  profile: "essentials" | "wider",
  over: Partial<Itinerary> = {},
): Itinerary {
  const d1 = "00000000-0000-4000-8000-0000000000d1";
  const d2 = "00000000-0000-4000-8000-0000000000d2";
  const base = makeSummary(profile);
  return {
    ...base,
    days: [
      {
        id: d1,
        day_index: 1,
        date: "2027-05-01",
        base_city_id: null,
        items: [
          item(d1, 1, {
            id: "i1",
            name: "Schönbrunn Palace",
            lat: 48.1845,
            lon: 16.3122,
            start: "09:00:00",
            end: "11:00:00",
            minutes: 120,
            reasons: ["A well-known sight.", "Close to the previous stop."],
            transfer: { to: "i2", seconds: 1260, meters: 1500, confidence: "estimated" },
          }),
          item(d1, 2, {
            id: "i2",
            name: "Belvedere",
            lat: 48.1916,
            lon: 16.3808,
            start: "11:21:00",
            end: "12:51:00",
            minutes: 90,
            source: "user",
            transfer: { to: "i3", mode: "drive", seconds: 600, meters: 4200, confidence: "routed" },
          }),
          item(d1, 3, {
            id: "i3",
            name: "St. Stephen's Cathedral",
            lat: 48.2085,
            lon: 16.3731,
            start: "13:01:00",
            end: "14:01:00",
            minutes: 60,
          }),
        ],
      },
      {
        id: d2,
        day_index: 2,
        date: "2027-05-02",
        base_city_id: null,
        items: [
          item(d2, 1, {
            id: "j1",
            name: "Hofburg",
            lat: 48.2065,
            lon: 16.3664,
            start: "09:00:00",
            end: "10:30:00",
            minutes: 90,
            transfer: { to: "j2", seconds: 300, meters: 380, confidence: "routed" },
          }),
          item(d2, 2, {
            id: "j2",
            name: "Albertina",
            lat: 48.2047,
            lon: 16.3686,
            start: "10:35:00",
            end: "12:05:00",
            minutes: 90,
          }),
        ],
      },
    ],
    ...over,
  } as unknown as Itinerary;
}

export function makeDestination(over: Partial<DestinationResult> = {}): DestinationResult {
  return {
    kind: "city",
    ref: "900101",
    name: "Vienna",
    country_iso2: "AT",
    country_name: "Austria",
    admin1_name: "Vienna",
    population: 1900000,
    admin_level: null,
    lat: 48.2082,
    lon: 16.3738,
    region_id: "austria",
    planning_available: true,
    match: "exact",
    ...over,
  } as DestinationResult;
}
