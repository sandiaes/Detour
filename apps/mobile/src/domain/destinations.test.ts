import type { ExternalPlace } from "@detour/shared";

import { makeDestination, makeTrip } from "../testing/fixtures";
import { coverSources } from "../screens/TripOverviewScreen";
import {
  choiceFromExternal,
  isPlannable,
  manualChoice,
  manualPoint,
  placeCoverSource,
  tripBody,
} from "./destinations";

const photon: ExternalPlace = {
  provider: "photon",
  ref: "N42",
  name: "Hallstatt",
  lat: 47.5622,
  lon: 13.6493,
  osm_key: "place",
  osm_value: "village",
  country_code: "AT",
  country: "Austria",
  state: "Upper Austria",
  city: null,
  street: null,
  housenumber: null,
  postcode: null,
  licence: "ODbL-1.0",
};

test("a Photon result is a place with a provider reference and is never plannable", () => {
  const c = choiceFromExternal(photon)!;
  expect(c).toMatchObject({ kind: "place", ref: "photon:N42", admin1_name: "Upper Austria" });
  expect(isPlannable(c)).toBe(false);
  expect(choiceFromExternal({ ...photon, ref: null })).toBeNull(); // nothing to refer to
});

test("a plannable result stays a city or area trip; others become place trips", () => {
  const vienna = makeDestination();
  const start = { days: 3, startDate: null };
  expect(isPlannable(vienna)).toBe(true);
  expect(tripBody(vienna, start, false)).toEqual({
    title: "Vienna",
    destination_kind: "city",
    destination_ref: "900101",
    duration_days: 3,
    start_date: null,
  });
  expect(tripBody(vienna, start, true)).toMatchObject({
    destination_kind: "place",
    destination_ref: "geonames:900101",
    destination_name: "Vienna",
    destination_country: "AT",
  });
  const area = makeDestination({ kind: "area", ref: "abc" });
  expect(tripBody(area, start, true)).toMatchObject({ destination_ref: "area:abc" });
});

test("a manual destination needs both coordinates, a decimal comma is accepted", () => {
  expect(manualChoice("Ort")).toMatchObject({ kind: "place", ref: "manual" });
  expect(manualPoint("47,5", "13.6")).toEqual({ lat: 47.5, lon: 13.6 });
  expect(manualPoint("91", "13")).toBeNull();
  expect(manualPoint("47", "")).toBeNull();
});

test("only a gazetteer place has photo candidates", () => {
  const trip = (ref: string) =>
    makeTrip({
      destination: { kind: "place", ref, name: "X", lat: 1, lon: 2, country_iso2: null },
    });
  expect(placeCoverSource(trip("geonames:123"))).toEqual({ kind: "city", ref: "123", name: "X" });
  expect(placeCoverSource(trip("area:u-1"))).toEqual({ kind: "area", ref: "u-1", name: "X" });
  expect(coverSources(trip("photon:N1"))).toEqual([]);
  expect(coverSources(trip("manual"))).toEqual([]);
});
