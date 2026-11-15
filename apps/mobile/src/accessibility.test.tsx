import { fireEvent, render, screen, within } from "@testing-library/react-native";
import { Dimensions, StyleSheet } from "react-native";

import { AppContent } from "./App";
import { createMemoryStore } from "./cache/store";
import { createMemoryDocumentStore } from "./documents/store";
import { createFakeClient } from "./testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeArchiveInfo,
  makeArchivedVisits,
  makeDestination,
  makeItinerary,
  makePastTrip,
  makePlaceSuggestions,
  makeSummary,
  makeTrip,
} from "./testing/fixtures";
import { Harness } from "./testing/harness";

type Host = ReturnType<typeof screen.getByRole>;

function textOf(el: Host): string {
  return within(el)
    .queryAllByText(/./)
    .map((t) => String(t.props.children))
    .join(" ");
}

/** The size a touch lands on: the element's own height plus its hit slop. */
function touchHeight(el: Host): number {
  const style = StyleSheet.flatten(el.props.style) ?? {};
  const own = Math.max(Number(style.minHeight ?? 0), Number(style.height ?? 0));
  const slop = el.props.hitSlop ?? {};
  return own + Number(slop.top ?? 0) + Number(slop.bottom ?? 0);
}

/** Every control on screen has a spoken name and a touch target of at least 48 dp. */
function checkControls() {
  const controls = [
    ...screen.queryAllByRole("button"),
    ...screen.queryAllByRole("link"),
    ...screen.queryAllByRole("tab"),
  ] as Host[];
  expect(controls.length).toBeGreaterThan(0);
  for (const el of controls) {
    const name = el.props.accessibilityLabel || textOf(el);
    expect({ name, empty: name.trim() === "" }).toMatchObject({ empty: false });
    expect({ name, height: touchHeight(el) >= 48 }).toEqual({ name, height: true });
  }
}

function server() {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip()],
    "GET /v1/trips/{trip_id}/itineraries": () => [makeSummary("essentials"), makeSummary("wider")],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "GET /v1/attributions": () => [],
    "GET /v1/destinations/search": () => ({
      query: "Vie",
      results: [makeDestination(), makeDestination({ ref: "a", name: "Area", kind: "area" })],
      external: { state: "not_requested", results: [] },
    }),
  });
}

async function show(initial: Parameters<typeof Harness>[0]["initial"], ready: string | RegExp) {
  await render(
    <Harness client={server()} cache={createMemoryStore()} initial={initial}>
      <AppContent />
    </Harness>,
  );
  await screen.findByText(ready);
}

// A phone-width window.
beforeEach(() =>
  Dimensions.set({
    window: { width: 360, height: 740, scale: 2, fontScale: 1 },
    screen: { width: 360, height: 740, scale: 2, fontScale: 1 },
  }),
);

test("trips list", async () => {
  await show({ name: "trips" }, "Vienna");
  checkControls();
});

test("trips list: the Past tab", async () => {
  await show({ name: "trips" }, "Vienna");
  await fireEvent.press(screen.getByRole("tab", { name: "Past" }));
  await screen.findByText("No past trips yet");
  checkControls();
});

test("trip overview, each of its tabs, its menu and the Add sheet", async () => {
  await render(
    <Harness
      client={createFakeClient({
        "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
        "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
      })}
      initial={{ name: "tripOverview", tripId: TRIP_ID }}
    >
      <AppContent />
    </Harness>,
  );
  await screen.findByTestId("day-row-1");
  checkControls();
  for (const tab of ["Map", "Trip photos", "Trip documents"]) {
    await fireEvent.press(screen.getByRole("tab", { name: tab }));
    expect(screen.getByRole("tab", { name: tab }).props.accessibilityState).toMatchObject({
      selected: true,
    });
    checkControls();
  }
  await fireEvent.press(screen.getByRole("button", { name: "Trip menu" }));
  await screen.findByRole("header", { name: "Trip menu" });
  checkControls();
  await fireEvent.press(screen.getAllByRole("button", { name: "Close" })[1] as Host);
  await fireEvent.press(screen.getByRole("button", { name: "Add to this trip" }));
  await screen.findByRole("header", { name: "Add to this trip" });
  checkControls();
});

test("add a place: search results and the suggested days", async () => {
  await render(
    <Harness
      client={createFakeClient({
        "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
        "GET /v1/places/search": () => ({
          query: "Prat",
          results: [
            {
              id: "00000000-0000-4000-8000-00000000ab01",
              name: "Prater",
              kind: "attraction",
              category: "theme_park",
              lat: 48.2,
              lon: 16.39,
              region_id: "austria",
              city_id: null,
              city_name: "Vienna",
              distance_m: 2300,
            },
          ],
          external: { state: "not_requested", provider: null, results: [] },
        }),
        "GET /v1/destinations/search": () => ({ query: "Prat", results: [] }),
        "POST /v1/itineraries/{itinerary_id}/place-suggestions": () => makePlaceSuggestions(),
      } as never)}
      initial={{ name: "addPlace", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID }}
    >
      <AppContent />
    </Harness>,
  );
  await fireEvent.changeText(screen.getByLabelText("Sight or town"), "Prat");
  await fireEvent.press(await screen.findByLabelText(/^Prater, theme park/, {}, { timeout: 3000 }));
  checkControls();
  await fireEvent.press(screen.getByTestId("find-days"));
  await screen.findByTestId("place-suggestions");
  checkControls();
  await fireEvent.press(screen.getByRole("tab", { name: "Address" }));
  checkControls();
});

test("documents: the list, the form with a place chosen, and a document", async () => {
  const documents = createMemoryDocumentStore([
    {
      id: "doc-1",
      tripId: TRIP_ID,
      title: "Travel policy",
      category: "other",
      link: { kind: "trip" },
      fileName: "policy.pdf",
      mimeType: "application/pdf",
      sizeBytes: 50_000,
      uri: "file:///policy.pdf",
      createdAt: 1,
    },
  ]);
  await render(
    <Harness
      client={createFakeClient({
        "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
        "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
      })}
      documents={documents}
      initial={{ name: "tripOverview", tripId: TRIP_ID, section: "documents" }}
    >
      <AppContent />
    </Harness>,
  );
  await screen.findByText("Travel policy");
  checkControls();
  await fireEvent.press(screen.getByTestId("add-document"));
  await fireEvent.press(await screen.findByTestId("choose-file"));
  await fireEvent.press(await screen.findByTestId("link-place"));
  checkControls();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  await fireEvent.press(await screen.findByText("Travel policy"));
  await screen.findByTestId("open-document");
  checkControls();
});

test("place detail", async () => {
  await show(
    { name: "placeDetail", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, itemId: "m1" },
    "Gasthaus Zum Test",
  );
  checkControls();
});

test("trip overview: a day on the map with a stop chosen", async () => {
  await render(
    <Harness
      client={createFakeClient({
        "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
        "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
      })}
      initial={{ name: "tripOverview", tripId: TRIP_ID, section: "overview" }}
    >
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByTestId("day-row-1"));
  await fireEvent.press(await screen.findByTestId("stop-i1"));
  await screen.findByTestId("details-i1");
  checkControls();
});

test.each([
  ["explore", "Explore is planned"],
  ["photos", "Trip photos are planned"],
  ["more", "Settings"],
] as const)("the %s tab", async (name, ready) => {
  await show({ name }, ready);
  checkControls();
});

test("create trip form with search results", async () => {
  await show({ name: "createTrip" }, "Public transport");
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  await screen.findByText("Area", {}, { timeout: 3000 });
  checkControls();
});

test("proposals", async () => {
  await show({ name: "trip", tripId: TRIP_ID }, "Choose your itinerary");
  checkControls();
});

test("day list", async () => {
  await show(
    { name: "itinerary", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, view: "days", day: 1 },
    "Schönbrunn Palace",
  );
  checkControls();
});

test("map with markers and the attribution links", async () => {
  await show(
    { name: "itinerary", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, view: "map", day: 1 },
    "Schönbrunn Palace",
  );
  expect(screen.getAllByLabelText(/^Stop \d+, (Attraction|Restaurant|Café): /).length).toBe(5);
  checkControls();
  await fireEvent.press(screen.getByRole("button", { name: "Map key" }));
  await screen.findByText("Restaurant or café");
  checkControls();
});

function pastServer() {
  return createFakeClient({
    "GET /v1/trips": () => [makePastTrip()],
    "GET /v1/trips/{trip_id}/visits": () => makeArchivedVisits(),
    "GET /v1/trips/{trip_id}/archive": () => makeArchiveInfo(),
  });
}

test("past trip: map with markers", async () => {
  await render(
    <Harness client={pastServer()} initial={{ name: "pastTrip", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  await screen.findByLabelText("Day 1");
  expect(screen.getAllByLabelText(/^(City|Attraction), day \d+: /).length).toBe(5);
  checkControls();
});

test("past trip: list by city, every skip control named for its place", async () => {
  await render(
    <Harness client={pastServer()} initial={{ name: "pastTrip", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByRole("tab", { name: "Show the list by city" }));
  await screen.findByText("Kunsthaus Graz");
  expect(screen.getAllByRole("button", { name: /^Mark .+ as skipped$/ })).toHaveLength(5);
  checkControls();
});

test("settings", async () => {
  await show({ name: "settings" }, /detour-api 0\.1\.0/);
  checkControls();
});

test("nothing is conveyed by colour alone: states carry words or marks", async () => {
  await show({ name: "trip", tripId: TRIP_ID }, "Choose your itinerary");
  // Selected, estimated and offline each have a word in the text, checked elsewhere; this guards
  // the shared controls: an open comparison is announced as expanded and changes its icon.
  const compare = screen.getByRole("button", { name: "Compare itineraries" });
  expect(compare.props.accessibilityState).toMatchObject({ expanded: false });
  await fireEvent.press(compare);
  expect(
    screen.getByRole("button", { name: "Compare itineraries" }).props.accessibilityState,
  ).toMatchObject({ expanded: true });
});

// ---- the screens the first version of this file did not visit ------------------------------------

async function showHeader(
  initial: Parameters<typeof Harness>[0]["initial"],
  header: string | RegExp,
  client = server(),
) {
  await render(
    <Harness client={client} cache={createMemoryStore()} initial={initial}>
      <AppContent />
    </Harness>,
  );
  await screen.findByRole("header", { name: header });
}

function planServer() {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/trips/{trip_id}/itineraries": () => [makeSummary("essentials"), makeSummary("wider")],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials"),
    "GET /v1/itineraries/{itinerary_id}/versions": () => [],
    "GET /v1/attributions": () => [],
  } as never);
}

test("more, explore and photos: planned rows are dimmed buttons that say why", async () => {
  await showHeader({ name: "more" }, "More");
  checkControls();
  for (const name of [/^Saved places\./, /^Travel preferences\./, /^Archive trip\./]) {
    const row = screen.getByRole("button", { name });
    expect(row.props.accessibilityState).toMatchObject({ disabled: true });
    expect(row.props.accessibilityLabel).toMatch(/Coming later$/);
  }
  for (const header of ["Explore", "Photos"]) {
    await fireEvent.press(screen.getByRole("tab", { name: header }));
    await screen.findByRole("header", { name: header });
    checkControls();
  }
});

test("export, import and image credits", async () => {
  await showHeader({ name: "exportTrips" }, "Back up all trips", planServer());
  checkControls();
  await showHeader({ name: "importTrips" }, "Import a trip", planServer());
  checkControls();
  await showHeader({ name: "imageCredits" }, "Image credits", planServer());
  checkControls();
});

test("trip settings: the red entry points and both confirmation sheets", async () => {
  await showHeader({ name: "tripSettings", tripId: TRIP_ID }, "Trip settings", planServer());
  checkControls();
  for (const [entry, title, confirm, back] of [
    [/^Mark the trip/, "Mark as a past trip?", "Yes, mark as past", "Keep planning"],
    [/^Delete the trip/, "Delete this trip?", "Yes, delete the trip", "Keep the trip"],
  ] as const) {
    await fireEvent.press(await screen.findByRole("button", { name: entry }));
    await screen.findByRole("header", { name: title });
    // The sheet's own controls: a red confirm, a way back and Close, each named and 48 dp.
    expect(screen.getByRole("button", { name: confirm })).toBeOnTheScreen();
    checkControls();
    await fireEvent.press(screen.getByRole("button", { name: back }));
    expect(screen.queryByRole("header", { name: title })).toBeNull();
  }
});

test("optimize and add a restaurant", async () => {
  await showHeader(
    { name: "optimize", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID },
    /^Optimize/,
    planServer(),
  );
  checkControls();
  await showHeader(
    { name: "addRestaurant", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID },
    /^Add a restaurant or café/,
    planServer(),
  );
  checkControls();
});

test("add a document: the first step with its options", async () => {
  await showHeader({ name: "documentForm", tripId: TRIP_ID }, "Add document", planServer());
  checkControls();
});
