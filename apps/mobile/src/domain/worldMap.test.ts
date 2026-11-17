import type { Trip } from "@detour/shared";

import { worldPoints, worldSummary } from "./worldMap";

function trip(over: Partial<Trip> & { id: string }): Trip {
  return {
    title: "Trip",
    destination: { kind: "city", ref: "1", name: "Vienna", lat: 48.2, lon: 16.37 },
    duration_days: 3,
    start_date: null,
    end_date: null,
    selected_itinerary_id: null,
    status: "active",
    archived_at: null,
    is_seed: false,
    stops_version: 0,
    uses_car: true,
    role: "owner",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  } as Trip;
}

test("a past trip is been, any other trip is going, the seed trip is left out", () => {
  const points = worldPoints([
    trip({ id: "a", status: "past" }),
    trip({
      id: "b",
      destination: { kind: "city", ref: "2", name: "Rome", lat: 41.9, lon: 12.5 },
    }),
    trip({ id: "s", is_seed: true }),
  ]);
  expect(worldSummary(points)).toEqual({ been: 1, going: 1 });
});

test("a city on two trips is one point, going if any trip to it is not past", () => {
  const points = worldPoints([
    trip({ id: "a", status: "past", created_at: "2025-01-01T00:00:00Z" }),
    trip({ id: "b" }),
  ]);
  expect(points).toHaveLength(1);
  expect(points[0]!.state).toBe("going");
  expect(points[0]!.trips.map((t) => t.id)).toEqual(["b", "a"]);
});

test("a multi-city trip contributes each of its cities", () => {
  const stops = [
    { position: 1, city_id: 1, name: "Rome", country_iso2: "IT", lat: 41.9, lon: 12.5, days: 2 },
    {
      position: 2,
      city_id: 2,
      name: "Florence",
      country_iso2: "IT",
      lat: 43.8,
      lon: 11.2,
      days: 2,
    },
  ];
  expect(
    worldPoints([trip({ id: "a", stops })])
      .map((p) => p.name)
      .sort(),
  ).toEqual(["Florence", "Rome"]);
});
