import type { CoverCandidate } from "@detour/shared";
import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import { photoPlacement } from "../components/ds/Cover";
import { createFakeClient } from "../testing/fakeClient";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeDestination,
  makeItinerary,
  makePhoto,
  makeSummary,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";
import { SEARCH_DEBOUNCE_MS } from "./CreateTripScreen";
import { collectPhotos } from "./ImageCreditsScreen";
import { commonsFileOf, coverSources, firstPhoto } from "./TripOverviewScreen";

// Photos that fit their frame, "Change photo", image credits and day thumbnails (ADR 022
// amendment, decisions e, g to j).

function candidate(name: string, over: Partial<CoverCandidate> = {}): CoverCandidate {
  return {
    commons_file: name,
    preview_url: `/v1/cover-previews/${name.length}`,
    width: 1600,
    height: 1200,
    credit: {
      author: `Author of ${name}`,
      licence: "CC BY 4.0",
      licence_url: "https://creativecommons.org/licenses/by/4.0",
      source_url: `https://commons.wikimedia.org/wiki/File:${name.replace(/ /g, "_")}`,
      text: `Photo: Author of ${name}, CC BY 4.0, Wikimedia Commons (resized)`,
    },
    ...over,
  };
}

test("a landscape photo is centred and a portrait photo is anchored toward its top", () => {
  // A 3:2 landscape photo in a 2:1 frame: full width, cropped equally above and below.
  const l = photoPlacement({ width: 400, height: 200 }, { width: 1080, height: 720 });
  expect(l.width).toBeCloseTo(400);
  expect(l.height).toBeCloseTo(800 / 3);
  expect(l.left).toBeCloseTo(0);
  expect(l.top).toBeCloseTo(-(800 / 3 - 200) / 2);
  // A 2:3 portrait photo in the same frame: full width, a third of the overflow above.
  const p = photoPlacement({ width: 400, height: 200 }, { width: 720, height: 1080 });
  expect(p.width).toBe(400);
  expect(p.height).toBe(600);
  expect(p.top).toBeCloseTo(-400 / 3);
  // A photo narrower than a tall frame fills the height and is centred sideways.
  const q = photoPlacement({ width: 100, height: 300 }, { width: 1080, height: 720 });
  expect(q.height).toBe(300);
  expect(q.left).toBeCloseTo(-(450 - 100) / 2);
  // Nothing measured yet: the frame itself.
  expect(photoPlacement({ width: 0, height: 0 }, { width: 10, height: 10 })).toEqual({
    width: 0,
    height: 0,
    left: 0,
    top: 0,
  });
});

test("the cover can be changed from the trip menu", async () => {
  const chosen: string[] = [];
  const client = createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: "selected" }),
      makeSummary("wider"),
    ],
    "GET /v1/destinations/{kind}/{ref}/cover-candidates": () => [
      candidate("Stephansdom.jpg"),
      candidate("Ring tower.jpg", { width: 1200, height: 1800 }),
    ],
    "PUT /v1/trips/{trip_id}/cover": ({ body }) => {
      chosen.push(String((body as { commons_file: string | null }).commons_file));
      return makeTrip({ selected_itinerary_id: ESSENTIALS_ID, cover_image: makePhoto() });
    },
  } as never);
  await render(
    <Harness client={client} initial={{ name: "tripOverview", tripId: TRIP_ID }}>
      <AppContent />
    </Harness>,
  );
  fireEvent.press(await screen.findByTestId("trip-menu"));
  fireEvent.press(await screen.findByTestId("menu-change-photo"));
  expect(await screen.findByLabelText("Photo by Author of Ring tower.jpg, CC BY 4.0")).toBeTruthy();
  expect(client.calls.find((c) => c.path.includes("cover-candidates"))?.params).toEqual({
    kind: "city",
    ref: "900101",
  });
  fireEvent.press(screen.getByTestId("cover-candidate-Ring tower.jpg"));
  await screen.findByTestId("trip-cover");
  expect(chosen).toEqual(["Ring tower.jpg"]);
});

test("a cover chosen on the new-trip screen is set right after the trip is created", async () => {
  const order: string[] = [];
  const stored: unknown[] = [];
  const client = createFakeClient({
    "GET /v1/trips": () => stored,
    "GET /v1/destinations/search": () => ({
      query: "vie",
      external: { state: "not_requested", results: [] },
      results: [makeDestination({ ref: "900101" })],
    }),
    "GET /v1/destinations/{kind}/{ref}/cover-candidates": () => [candidate("Stephansdom.jpg")],
    "POST /v1/trips": () => {
      order.push("create");
      stored.unshift(makeTrip({ selected_itinerary_id: ESSENTIALS_ID }));
      return makeTrip();
    },
    "PUT /v1/trips/{trip_id}/cover": ({ body }) => {
      order.push(`cover ${(body as { commons_file: string }).commons_file}`);
      return makeTrip({ cover_image: makePhoto() });
    },
    "POST /v1/trips/{trip_id}/itineraries": () => makeItinerary("essentials"),
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: "selected" }),
    ],
    "PATCH /v1/trips/{trip_id}": () => makeTrip({ selected_itinerary_id: ESSENTIALS_ID }),
  } as never);
  await render(
    <Harness client={client} initial={{ name: "createTrip" }}>
      <AppContent />
    </Harness>,
  );
  jest.useFakeTimers();
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10);
  });
  jest.useRealTimers();
  fireEvent.press(await screen.findByText("Vienna"));
  fireEvent.press(await screen.findByTestId("change-photo"));
  fireEvent.press(await screen.findByTestId("cover-candidate-Stephansdom.jpg"));
  expect(await screen.findByText("Photo: Author of Stephansdom.jpg, CC BY 4.0")).toBeTruthy();
  fireEvent.press(screen.getByText("Start with an empty trip"));
  await screen.findByTestId("trip-cover");
  expect(order).toEqual(["create", "cover Stephansdom.jpg"]);
});

test("image credits list every photo the app holds, once each", () => {
  const a = makePhoto();
  const b = makePhoto({
    id: "b",
    url: "/v1/images/b",
    credit: { ...a.credit, author: "Ann Other" },
  });
  const photos = collectPhotos([
    [{ cover_image: a }, { cover_image: null }],
    { days: [{ items: [{ image: b }, { image: a }] }] },
  ]);
  expect(photos.map((p) => p.credit.author)).toEqual(["Ann Other", "Jane Doe"]);
});

test("a day's thumbnail is the photo of its first visit that has one", () => {
  const day = makeItinerary("essentials").days[0]!;
  expect(firstPhoto({ ...day, items: day.items.map((i) => ({ ...i, image: null })) })).toBeNull();
  const photo = makePhoto();
  const items = day.items.map((i, n) => ({ ...i, image: n === 1 ? photo : null }));
  const visitIndex = items.findIndex((i) => i.type === "visit" && i.image);
  expect(firstPhoto({ ...day, items })).toEqual(visitIndex >= 0 ? photo : null);
});

test("the chosen file is read back from the photo's page", () => {
  expect(commonsFileOf("https://commons.wikimedia.org/wiki/File:Wien_-_Dom%C3%A4.jpg")).toBe(
    "Wien - Domä.jpg",
  );
  expect(commonsFileOf(undefined)).toBeNull();
  expect(coverSources(makeTrip())).toEqual([{ kind: "city", ref: "900101", name: "Vienna" }]);
});
