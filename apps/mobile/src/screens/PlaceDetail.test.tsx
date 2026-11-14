import type { Itinerary } from "@detour/shared";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { createFakeClient } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeChangeSet,
  makeItinerary,
  makePhoto,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { findItem, formatAddress, formatCoordinates } from "./PlaceDetailScreen";

const PLACE_ID = "00000000-0000-4000-8000-00000000a001";
const USER_PLACE_ID = "00000000-0000-4000-8000-0000000000b1";

function plan(): Itinerary {
  const p = makeItinerary("essentials", { status: "selected" });
  const items = p.days[0]!.items;
  items[0]!.place_id = PLACE_ID; // Schönbrunn Palace
  items[2]!.place_id = PLACE_ID; // Gasthaus Zum Test (the same id is enough for these tests)
  items[1]!.user_place_id = USER_PLACE_ID; // Belvedere, added by the user
  items[1]!.origin = "user";
  return p;
}

function server(handlers: Record<string, unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": plan,
    "GET /v1/places/{place_id}": () => ({
      id: PLACE_ID,
      name: "Schloss Schönbrunn",
      kind: "attraction",
      category: "palace",
      lat: 48.1845,
      lon: 16.3122,
      region_id: "at",
      city_id: 900101,
      city_name: "Vienna",
      cuisines: null,
      venue_type: null,
      distance_m: null,
      match: null,
      names_i18n: null,
      address: {
        street: "Schönbrunner Schloßstraße",
        housenumber: "47",
        postcode: "1130",
        city: "Wien",
      },
      meal_types: null,
      diet_flags: ["vegetarian"],
      default_visit_minutes: null,
      is_active: true,
      wikidata_id: null,
      sources: [
        {
          source: "osm",
          source_ref: "way/1",
          licence: "ODbL-1.0",
          attribution: "© OpenStreetMap contributors",
        },
      ],
    }),
    "GET /v1/user-places/{place_id}": () => ({
      id: USER_PLACE_ID,
      kind: "attraction",
      name: "Belvedere",
      lat: 48.1916,
      lon: 16.3808,
      cuisines: null,
      meal_types: null,
      source: "manual",
      search_provider: null,
      search_ref: null,
      created_at: "2026-11-12T10:00:00Z",
      updated_at: "2026-11-12T10:00:00Z",
    }),
    ...handlers,
  } as never);
}

async function open(itemId: string, client = server()) {
  await render(
    <Harness
      client={client}
      initial={{ name: "placeDetail", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, itemId }}
    >
      <AppContent />
    </Harness>,
  );
  return client;
}

test("an attraction shows when and where without labels, and no opening hours or reasons", async () => {
  const client = await open("i1");
  expect(await screen.findByRole("header", { name: "Schönbrunn Palace" })).toBeOnTheScreen();
  expect(screen.getByText(/^Attraction/)).toBeOnTheScreen();
  expect(screen.getByText("Day 1")).toBeOnTheScreen();
  expect(screen.getByText("Sat 1 May")).toBeOnTheScreen();
  expect(screen.getByText("2 h")).toBeOnTheScreen();
  expect(screen.getByText("Typical visit")).toBeOnTheScreen();
  expect(await screen.findByText("Schönbrunner Schloßstraße 47, 1130 Wien")).toBeOnTheScreen();
  for (const gone of ["When", "Duration", "Location", "Opening hours", "Not checked"]) {
    expect(screen.queryByText(gone)).toBeNull();
  }
  expect(screen.queryByText("Why it is in the plan")).toBeNull();
  expect(screen.queryByText("• A well-known sight.")).toBeNull();
  expect(screen.getByText("Data: © OpenStreetMap contributors (ODbL-1.0).")).toBeOnTheScreen();
  // Nothing invented: no price, rating or description.
  expect(screen.queryByText(/€|EUR|price|rating|★/i)).toBeNull();
  // Notes, photos and tickets are planned and say so.
  expect(screen.getByTestId("place-planned")).toBeOnTheScreen();
  expect(client.calls.find((c) => c.path === "/v1/places/{place_id}")?.params.place_id).toBe(
    PLACE_ID,
  );
});

test("a restaurant shows its meal, type and cuisine, and reservations as planned", async () => {
  await open("m1");
  expect(await screen.findByRole("header", { name: "Gasthaus Zum Test" })).toBeOnTheScreen();
  expect(screen.getAllByText(/^Restaurant/).length).toBeGreaterThanOrEqual(2); // kind line and type
  expect(screen.getByText("Lunch")).toBeOnTheScreen();
  expect(screen.getByLabelText("Type: Restaurant.")).toBeOnTheScreen();
  expect(screen.getByText("Regional, coffee shop")).toBeOnTheScreen();
  expect(await screen.findByText("vegetarian")).toBeOnTheScreen();
  expect(screen.getByText("Notes, photos and reservations")).toBeOnTheScreen();
  expect(screen.getByText("Bookings and documents")).toBeOnTheScreen();
  // Opening hours are a sight's concern here; a meal has its planned window instead.
  expect(screen.queryByText("Not checked")).toBeNull();
  expect(screen.queryByText(/€|EUR|price|rating/i)).toBeNull();
});

test("a restaurant with no cuisine in the data says so", async () => {
  await open("m2");
  expect(await screen.findByText("Cuisine not specified")).toBeOnTheScreen();
  expect(screen.getByText("Dinner")).toBeOnTheScreen();
});

test("a place the user added says so", async () => {
  await open("i2");
  expect(await screen.findByText("A place you added.")).toBeOnTheScreen();
  expect(screen.getByText("Added by you")).toBeOnTheScreen();
  expect(screen.getByText("1 h 30 min")).toBeOnTheScreen();
});

test("without an address the position is shown, never a made-up address", async () => {
  await open("i3");
  expect(await screen.findByText("Vienna")).toBeOnTheScreen();
  expect(screen.queryByText(/Straße|street/i)).toBeNull();
});

test("Show on the map opens the day's map with the stop highlighted", async () => {
  await open("i3");
  await fireEvent.press(await screen.findByTestId("show-on-map"));
  expect(await screen.findByTestId("map")).toBeOnTheScreen();
  expect(
    screen.getByLabelText("Stop 4, Attraction: St. Stephen's Cathedral").props.accessibilityState,
  ).toEqual({ selected: true });
  expect(screen.getByTestId("stop-i3").props.accessibilityState).toMatchObject({ selected: true });
});

test("lock and remove work from the details too", async () => {
  const client = await open(
    "i1",
    server({
      "PATCH /v1/items/{item_id}": (c: {
        params: { item_id: string };
        body: { locked: boolean };
      }) => ({
        id: c.params.item_id,
        locked: c.body.locked,
      }),
      "POST /v1/itineraries/{itinerary_id}/change-sets": () =>
        makeChangeSet({ action: "remove_place", target_name: "Schönbrunn Palace" }),
    }),
  );
  await fireEvent.press(await screen.findByLabelText("Lock Schönbrunn Palace"));
  expect(client.calls.find((c) => c.method === "PATCH")?.body).toEqual({ locked: true });
  expect(await screen.findByText("Locked")).toBeOnTheScreen();
  expect(screen.getByLabelText("Remove Schönbrunn Palace")).toBeDisabled();
  await fireEvent.press(screen.getByLabelText("Unlock Schönbrunn Palace"));
  await fireEvent.press(await screen.findByLabelText("Remove Schönbrunn Palace"));
  expect(await screen.findByText("Remove Schönbrunn Palace?")).toBeOnTheScreen();
});

test("a stop that is no longer in the plan says so", async () => {
  await open("gone");
  expect(await screen.findByText("Not in the plan any more")).toBeOnTheScreen();
});

describe("helpers", () => {
  test("formatAddress joins the open data's parts and leaves out what is missing", () => {
    expect(formatAddress({ street: "Hauptplatz", housenumber: "1", city: "Graz" })).toBe(
      "Hauptplatz 1, Graz",
    );
    expect(formatAddress({ postcode: "8010" })).toBe("8010");
    expect(formatAddress({})).toBeNull();
    expect(formatAddress(null)).toBeNull();
  });
  test("formatCoordinates uses five decimals", () => {
    expect(formatCoordinates(48.18451234, 16.3)).toBe("48.18451, 16.30000");
  });
  test("findItem finds the stop and its day", () => {
    const found = findItem(makeItinerary("essentials"), "j1");
    expect(found?.day.day_index).toBe(2);
    expect(found?.item.display_name).toBe("Hofburg");
    expect(findItem(makeItinerary("essentials"), "nope")).toBeNull();
  });
});

test("a place with a photo shows it and its credit; one without shows the illustration only", async () => {
  const withPhoto = plan();
  withPhoto.days[0]!.items[0]!.image = makePhoto();
  await open("i1", server({ "GET /v1/itineraries/{itinerary_id}": () => withPhoto }));
  expect(await screen.findByRole("header", { name: "Schönbrunn Palace" })).toBeOnTheScreen();
  expect(screen.getByTestId("cover-photo").props.source.uri).toMatch(/\/v1\/images\//);
  await fireEvent.press(screen.getByRole("button", { name: "Show the photo credit" }));
  expect(
    screen.getByText("Photo: Jane Doe, CC BY-SA 4.0, Wikimedia Commons (resized)"),
  ).toBeOnTheScreen();
});

test("a place without a photo shows no photo and no credit", async () => {
  await open("i1");
  expect(await screen.findByRole("header", { name: "Schönbrunn Palace" })).toBeOnTheScreen();
  expect(screen.queryByTestId("cover-photo", { includeHiddenElements: true })).toBeNull();
  expect(screen.queryByTestId("photo-credit")).toBeNull();
});

const NAMES = {
  display: "Schönbrunn Palace",
  local: "Schloss Schönbrunn",
  local_lang: "de",
  type: "established_english",
  source: "wikidata",
  confidence: 0.98,
  auto_generated: false,
  user_override: false,
} as const;

function namedPlan(names: Record<string, unknown>) {
  return () => {
    const p = plan();
    p.days[0]!.items[0]!.names = names as never;
    return p;
  };
}

test("the resolved English name leads and the local name stays under it (ADR 025)", async () => {
  await open("i1", server({ "GET /v1/itineraries/{itinerary_id}": namedPlan(NAMES) }));
  expect(await screen.findByRole("header", { name: "Schönbrunn Palace" })).toBeOnTheScreen();
  expect(screen.getByLabelText("Local name: Schloss Schönbrunn")).toBeOnTheScreen();
  expect(screen.queryByTestId("name-romanized")).toBeNull();
});

test("a name Detour romanized itself is labelled as such", async () => {
  const names = {
    ...NAMES,
    display: "Gyeongbokgung",
    local: "경복궁",
    local_lang: "ko",
    type: "automatic_transliteration",
    source: "detour",
    confidence: 0.7,
    auto_generated: true,
  };
  await open("i1", server({ "GET /v1/itineraries/{itinerary_id}": namedPlan(names) }));
  expect(await screen.findByRole("header", { name: "Gyeongbokgung" })).toBeOnTheScreen();
  expect(screen.getByLabelText("Local name: 경복궁")).toBeOnTheScreen();
  expect(screen.getByText("Automatically romanized")).toBeOnTheScreen();
});

test("edit display name saves the user's name for this place and can be undone", async () => {
  const client = server({
    "GET /v1/itineraries/{itinerary_id}": namedPlan(NAMES),
    "PUT /v1/places/{place_id}/display-name": () => ({
      ...NAMES,
      display: "The Palace",
      type: "user_override",
      source: "user",
      confidence: 1,
      user_override: true,
    }),
  });
  await open("i1", client);
  await fireEvent.press(await screen.findByTestId("edit-display-name"));
  const field = await screen.findByLabelText("Display name");
  await fireEvent.changeText(field, "  The Palace ");
  await fireEvent.press(screen.getByTestId("save-display-name"));
  expect(await screen.findByTestId("edit-display-name")).toBeOnTheScreen();
  const put = client.calls.find((c) => c.path === "/v1/places/{place_id}/display-name");
  expect(put?.method).toBe("PUT");
  expect(put?.params.place_id).toBe(PLACE_ID);
  expect(put?.body).toEqual({ name: "The Palace" });
});

test("an overridden name offers the usual name back", async () => {
  const client = server({
    "GET /v1/itineraries/{itinerary_id}": namedPlan({
      ...NAMES,
      display: "The Palace",
      type: "user_override",
      source: "user",
      confidence: 1,
      user_override: true,
    }),
    "DELETE /v1/places/{place_id}/display-name": () => NAMES,
  });
  await open("i1", client);
  await fireEvent.press(await screen.findByTestId("reset-display-name"));
  await screen.findByTestId("edit-display-name");
  expect(client.count("DELETE /v1/places/{place_id}/display-name")).toBe(1);
});
