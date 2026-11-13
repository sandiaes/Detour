import type {
  PlaceSuggestions,
  ArchiveInfo,
  ChangeSet,
  DestinationResult,
  Itinerary,
  ItinerarySummary,
  Trip,
  TripVisit,
} from "@detour/shared";

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
    meals: 1,
    meal_minutes: 60,
    intercity_legs: 0,
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
    meals: 3,
    meal_minutes: 180,
    intercity_legs: 1,
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
    engine_version: "planner-2.0.0",
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
  mealType?: "lunch" | "snack" | "dinner" | null;
  restaurant?: { venue_type: string | null; cuisines: string[] | null };
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
    restaurant: i.restaurant ?? null,
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
        base_city_id: 900101,
        base_city_name: "Vienna",
        base_city_lat: 48.2082,
        base_city_lon: 16.3738,
        arrival: null,
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
            transfer: { to: "m1", mode: "drive", seconds: 600, meters: 4200, confidence: "routed" },
          }),
          item(d1, 3, {
            id: "m1",
            name: "Gasthaus Zum Test",
            type: "meal",
            mealType: "lunch",
            lat: 48.2079,
            lon: 16.3725,
            start: "13:01:00",
            end: "14:01:00",
            minutes: 60,
            reasons: ["Lunch, planned between 12:00 and 14:30."],
            restaurant: { venue_type: "restaurant", cuisines: ["regional", "coffee_shop"] },
            transfer: { to: "i3", seconds: 120, meters: 90, confidence: "estimated" },
          }),
          item(d1, 4, {
            id: "i3",
            name: "St. Stephen's Cathedral",
            lat: 48.2085,
            lon: 16.3731,
            start: "14:03:00",
            end: "15:03:00",
            minutes: 60,
            transfer: { to: "m2", seconds: 240, meters: 300, confidence: "estimated" },
          }),
          item(d1, 5, {
            id: "m2",
            name: "Café Ohne Angabe",
            type: "meal",
            mealType: "dinner",
            lat: 48.2091,
            lon: 16.3711,
            start: "18:30:00",
            end: "20:00:00",
            minutes: 90,
            restaurant: { venue_type: "restaurant", cuisines: null },
          }),
        ],
      },
      {
        id: d2,
        day_index: 2,
        date: "2027-05-02",
        base_city_id: 900102,
        base_city_name: "Graz",
        base_city_lat: 47.0707,
        base_city_lon: 15.4395,
        arrival: {
          from_base_city_id: 900101,
          from_base_city_name: "Vienna",
          mode: "drive",
          seconds: 8400,
          meters: 191000,
          confidence: "estimated",
        },
        items: [
          item(d2, 1, {
            id: "j1",
            name: "Hofburg",
            lat: 48.2065,
            lon: 16.3664,
            start: "11:20:00",
            end: "12:50:00",
            minutes: 90,
            transfer: { to: "j2", seconds: 300, meters: 380, confidence: "routed" },
          }),
          item(d2, 2, {
            id: "j2",
            name: "Albertina",
            lat: 48.2047,
            lon: 16.3686,
            start: "12:55:00",
            end: "14:25:00",
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
    unavailable_reason: null,
    match: "exact",
    ...over,
  } as DestinationResult;
}

export const CHANGE_ID = "00000000-0000-4000-8000-0000000000c1";

export function makeChangeSet(over: Partial<ChangeSet> = {}): ChangeSet {
  return {
    id: CHANGE_ID,
    itinerary_id: ESSENTIALS_ID,
    action: "add_place",
    target_name: "Prater",
    status: "pending",
    base_version: 1,
    restores_version: null,
    result_version: null,
    diff: {
      added: [
        {
          day: 1,
          kind: "visit",
          name: "Prater",
          meal_type: null,
          start_time: "15:10:00",
          end_time: "16:10:00",
          added_by_you: true,
        },
      ],
      removed: [
        {
          day: 1,
          kind: "visit",
          name: "St. Stephen's Cathedral",
          meal_type: null,
          start_time: "14:03:00",
          end_time: "15:03:00",
          added_by_you: false,
        },
      ],
      moved: [
        {
          kind: "visit",
          name: "Belvedere",
          from_day: 1,
          to_day: 2,
          old_start_time: "11:21:00",
          new_start_time: "10:05:00",
        },
      ],
      retimed: [
        {
          kind: "meal",
          name: "Gasthaus Zum Test",
          day: 1,
          meal_type: "lunch",
          old_start_time: "13:01:00",
          new_start_time: "12:30:00",
        },
      ],
      base_changes: [],
      days_changed: [1, 2],
      travel_minutes_before: 40,
      travel_minutes_after: 58,
      travel_minutes_added: 18,
      estimated_legs: [
        { day: 1, from_name: "Schönbrunn Palace", to_name: "Prater", mode: "drive", minutes: 22 },
      ],
    },
    notes: [
      {
        code: "PLACE_ADDED",
        text: "You added Prater on day 1; the plan was recalculated around it.",
      },
    ],
    created_at: "2026-11-13T10:00:00Z",
    decided_at: null,
    ...over,
  } as ChangeSet;
}

// ---- past trips (ADR 006) ----------------------------------------------------------------------

export function makeVisit(
  over: Partial<TripVisit> & Pick<TripVisit, "id" | "kind" | "name">,
): TripVisit {
  return { lat: 47.07, lon: 15.44, geo_place_ref: null, day_number: 1, confirmed: true, ...over };
}

/** An area trip's archive: Graz on days 1 and 2, Leoben from day 3, in the archive's order. */
export function makeArchivedVisits(): TripVisit[] {
  return [
    makeVisit({ id: "v-graz", kind: "city", name: "Graz", lat: 47.0707, lon: 15.4395 }),
    makeVisit({
      id: "v-schlossberg",
      kind: "attraction",
      name: "Schlossberg",
      lat: 47.0737,
      lon: 15.4375,
    }),
    makeVisit({
      id: "v-kunsthaus",
      kind: "attraction",
      name: "Kunsthaus Graz",
      lat: 47.0714,
      lon: 15.4342,
      day_number: 2,
    }),
    makeVisit({
      id: "v-leoben",
      kind: "city",
      name: "Leoben",
      lat: 47.3833,
      lon: 15.0956,
      day_number: 3,
    }),
    makeVisit({
      id: "v-goess",
      kind: "attraction",
      name: "Stift Göss",
      lat: 47.3826,
      lon: 15.0914,
      day_number: 3,
    }),
  ];
}

export function makePastTrip(over: Partial<Trip> = {}): Trip {
  return makeTrip({
    id: TRIP_ID,
    title: "Styria, 4 days",
    destination: { kind: "area", ref: "area-1", name: "Styria", lat: 47.2, lon: 15.3 },
    duration_days: 4,
    end_date: "2027-05-04",
    status: "past",
    archived_at: "2027-05-06T08:00:00Z",
    selected_itinerary_id: null,
    ...over,
  });
}

export function makeArchiveInfo(over: Partial<ArchiveInfo> = {}): ArchiveInfo {
  return { trip_id: TRIP_ID, cities: 2, attractions: 3, skipped: 0, size_bytes: 4519, ...over };
}

const EMPTY_DIFF = {
  added: [],
  removed: [],
  moved: [],
  retimed: [],
  base_changes: [],
  days_changed: [],
  travel_minutes_before: 40,
  travel_minutes_after: 40,
  travel_minutes_added: 0,
  estimated_legs: [],
};

/** Three suggested days for adding Prater (ADR 021, step 4), best first. */
export function makePlaceSuggestions(over: Partial<PlaceSuggestions> = {}): PlaceSuggestions {
  const added = (day: number, start: string, end: string) => ({
    day,
    kind: "visit",
    name: "Prater",
    meal_type: null,
    start_time: start,
    end_time: end,
    added_by_you: true,
  });
  return {
    name: "Prater",
    duration_minutes: 120,
    duration_source: "category_default",
    days_considered: 2,
    issues: [],
    suggestions: [
      {
        rank: 1,
        day: 1,
        start_time: "15:10:00",
        end_time: "17:10:00",
        after_name: "St. Stephen's Cathedral",
        before_name: "Café Ohne Angabe",
        new_base_name: null,
        travel_minutes_added: 12,
        estimated: true,
        diff: {
          ...EMPTY_DIFF,
          added: [added(1, "15:10:00", "17:10:00")],
          days_changed: [1],
          travel_minutes_after: 52,
          travel_minutes_added: 12,
          retimed: [
            {
              kind: "meal",
              name: "Café Ohne Angabe",
              day: 1,
              meal_type: "dinner",
              old_start_time: "18:30:00",
              new_start_time: "19:00:00",
            },
          ],
        },
        reasons: [
          { code: "LEAST_TRAVEL", text: "Adds the least travel of the days that can take it." },
          { code: "NOTHING_LEFT_OUT", text: "Every planned visit stays in the plan." },
        ],
      },
      {
        rank: 2,
        day: 2,
        start_time: "10:05:00",
        end_time: "12:05:00",
        after_name: null,
        before_name: "Hofburg",
        new_base_name: null,
        travel_minutes_added: 35,
        estimated: false,
        diff: {
          ...EMPTY_DIFF,
          added: [added(2, "10:05:00", "12:05:00")],
          removed: [
            {
              day: 2,
              kind: "visit",
              name: "Kunsthaus",
              meal_type: null,
              start_time: "14:00:00",
              end_time: "15:00:00",
              added_by_you: false,
            },
          ],
          moved: [
            {
              kind: "visit",
              name: "Belvedere",
              from_day: 1,
              to_day: 2,
              old_start_time: "11:21:00",
              new_start_time: "15:00:00",
            },
          ],
          days_changed: [1, 2],
          travel_minutes_after: 75,
          travel_minutes_added: 35,
        },
        reasons: [
          { code: "MORE_TRAVEL", text: "Adds about 35 min of travel." },
          { code: "LEAVES_OUT", text: "Leaves out Kunsthaus to make room." },
        ],
      },
    ],
    ...over,
  } as PlaceSuggestions;
}
