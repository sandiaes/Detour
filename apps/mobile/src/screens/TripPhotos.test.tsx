import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { Linking } from "react-native";

import { AppContent } from "../App";
import { type TripExtras, createMemoryExtrasStore, emptyExtras } from "../documents/extras";
import { createFakeClient } from "../testing/fakeClient";
import { createFakeFiles } from "../testing/fakeFiles";
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

// A trip's Photos tab links the user's own albums, and a cover can come from the phone (ADR 031).

const PHOTOS = { name: "tripOverview", tripId: TRIP_ID, section: "photos" } as const;
const ALBUM = "https://photos.app.goo.gl/RomeTrip2027";
const ALBUM_ID = "00000000-0000-4000-8000-00000000a1b1";

type Album = { id: string; name: string; url: string; added_by: null; created_at: string };

/** The server's album links and cover (ADR 034, step 5), held between calls. */
function tripFiles(albums: Album[] = []) {
  let next = 1;
  return {
    "GET /v1/trips/{trip_id}/albums": () => albums,
    "POST /v1/trips/{trip_id}/albums": ({
      body,
    }: {
      body: { url: string; name: string | null };
    }) => {
      if (albums.some((a) => a.url === body.url)) {
        return { status: 409, body: { detail: "x", code: "album_exists" } };
      }
      const album: Album = {
        id: `00000000-0000-4000-8000-${String(next++).padStart(12, "0")}`,
        name: body.name ?? "Trip album",
        url: body.url,
        added_by: null,
        created_at: "2026-11-16T10:00:00Z",
      };
      albums.push(album);
      return album;
    },
    "PATCH /v1/trips/{trip_id}/albums/{album_id}": ({
      params,
      body,
    }: {
      params: { album_id: string };
      body: { name: string };
    }) => {
      const album = albums.find((a) => a.id === params.album_id);
      if (album) album.name = body.name;
      return album;
    },
    "DELETE /v1/trips/{trip_id}/albums/{album_id}": ({
      params,
    }: {
      params: { album_id: string };
    }) => {
      const at = albums.findIndex((a) => a.id === params.album_id);
      if (at >= 0) albums.splice(at, 1);
      return undefined;
    },
    "PUT /v1/trips/{trip_id}/own-cover": () => ({
      id: "00000000-0000-4000-8000-0000000c0c01",
      bytes: 4,
      uploaded_at: "2026-11-16T10:00:00Z",
    }),
    "DELETE /v1/trips/{trip_id}/own-cover": () => undefined,
  };
}

const ON_SERVER: Album = {
  id: ALBUM_ID,
  name: "Rome with Ana",
  url: ALBUM,
  added_by: null,
  created_at: "2026-11-16T10:00:00Z",
};

function server(handlers: Record<string, unknown> = {}, albums: Album[] = []) {
  return createFakeClient({
    ...tripFiles(albums),
    "GET /v1/trips": () => [
      makeTrip({ selected_itinerary_id: ESSENTIALS_ID, cover_image: makePhoto() }),
    ],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: "selected" }),
    ],
    "GET /v1/destinations/{kind}/{ref}/cover-candidates": () => [],
    "PUT /v1/trips/{trip_id}/cover": () => makeTrip({ selected_itinerary_id: ESSENTIALS_ID }),
    "DELETE /v1/trips/{trip_id}": () => undefined,
    ...handlers,
  } as never);
}

async function show(
  initial: Parameters<typeof Harness>[0]["initial"],
  opts: {
    extras?: ReturnType<typeof createMemoryExtrasStore>;
    files?: ReturnType<typeof createFakeFiles>;
    client?: ReturnType<typeof server>;
  } = {},
) {
  const extras = opts.extras ?? createMemoryExtrasStore();
  const files = opts.files ?? createFakeFiles();
  const client = opts.client ?? server();
  await render(
    <Harness client={client} initial={initial} extras={extras} files={files}>
      <AppContent />
    </Harness>,
  );
  return { extras, files, client };
}

const withAlbum = (over: Partial<TripExtras> = {}): TripExtras => ({
  ...emptyExtras(TRIP_ID),
  albums: [{ id: ALBUM_ID, name: "Rome with Ana", url: ALBUM, createdAt: 1 }],
  ...over,
});

let openURL: jest.SpyInstance;
beforeEach(() => {
  openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
});
afterEach(() => openURL.mockRestore());

test("an album is linked from its share message and opens in Google Photos", async () => {
  const { extras } = await show(PHOTOS);
  expect(await screen.findByText("No album linked yet")).toBeOnTheScreen();
  expect(screen.getByText(/Everyone on this trip sees the links/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("link-album"));
  expect(screen.getByText(/tap Share, then Copy link/)).toBeOnTheScreen();
  await fireEvent.changeText(
    screen.getByTestId("album-link"),
    `Check out "Rome" in Google Photos: ${ALBUM}`,
  );
  await fireEvent.changeText(screen.getByTestId("album-name"), "Rome with Ana");
  await fireEvent.press(screen.getByTestId("save-album"));
  const row = await screen.findByText("Rome with Ana");
  expect(screen.getByText("Google Photos · opens in Google Photos")).toBeOnTheScreen();
  const [saved] = (await extras.get(TRIP_ID)).albums;
  expect(saved).toMatchObject({ name: "Rome with Ana", url: ALBUM });
  await fireEvent.press(row);
  expect(openURL).toHaveBeenCalledWith(ALBUM);
});

test("a link that is not an https address is refused in words, and nothing is saved", async () => {
  const { extras } = await show(PHOTOS);
  await fireEvent.press(await screen.findByTestId("link-album"));
  await fireEvent.changeText(screen.getByTestId("album-link"), "our Rome album");
  await fireEvent.press(screen.getByTestId("save-album"));
  expect(await screen.findByText(/Paste the album's share link/)).toBeOnTheScreen();
  expect((await extras.get(TRIP_ID)).albums).toEqual([]);
});

test("the same album cannot be linked twice", async () => {
  await show(PHOTOS, {
    extras: createMemoryExtrasStore([withAlbum()]),
    client: server({}, [{ ...ON_SERVER }]),
  });
  await fireEvent.press(await screen.findByTestId("link-album"));
  await fireEvent.changeText(screen.getByTestId("album-link"), ALBUM);
  await fireEvent.press(screen.getByTestId("save-album"));
  expect(await screen.findByText(/already linked to the trip/)).toBeOnTheScreen();
});

test("an album can be renamed and its link removed, which leaves the album alone", async () => {
  const extras = createMemoryExtrasStore([withAlbum()]);
  await show(PHOTOS, { extras, client: server({}, [{ ...ON_SERVER }]) });
  await fireEvent.press(await screen.findByTestId(`album-menu-${ALBUM_ID}`));
  expect(screen.getByText(/does not delete the album/)).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByTestId("album-rename"), "Roma 2027");
  await fireEvent.press(screen.getByTestId("save-album-name"));
  expect(await screen.findByText("Roma 2027")).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId(`album-menu-${ALBUM_ID}`));
  await fireEvent.press(screen.getByTestId("remove-album"));
  expect(await screen.findByText("No album linked yet")).toBeOnTheScreen();
  expect((await extras.get(TRIP_ID)).albums).toEqual([]);
});

test("a link the phone cannot open says so", async () => {
  openURL.mockRejectedValue(new Error("no app"));
  await show(PHOTOS, {
    extras: createMemoryExtrasStore([withAlbum()]),
    client: server({}, [{ ...ON_SERVER }]),
  });
  await fireEvent.press(await screen.findByText("Rome with Ana"));
  expect(await screen.findByText(/could not open the album's link/)).toBeOnTheScreen();
});

test("the Photos screen lists every trip's albums", async () => {
  await show(
    { name: "photos" },
    { extras: createMemoryExtrasStore([withAlbum()]), client: server({}, [{ ...ON_SERVER }]) },
  );
  expect(await screen.findByTestId(`photos-trip-${TRIP_ID}`)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId(`photos-album-${ALBUM_ID}`));
  expect(openURL).toHaveBeenCalledWith(ALBUM);
});

// -- the cover from the phone --------------------------------------------------------------------

test("a picture from the phone becomes the cover for everyone, without a credit", async () => {
  const { extras, files, client } = await show({ name: "tripOverview", tripId: TRIP_ID });
  await screen.findByTestId("day-row-1");
  await fireEvent.press(screen.getByTestId("trip-menu"));
  await fireEvent.press(await screen.findByTestId("menu-change-photo"));
  expect(screen.getByText(/uploaded and shown to everyone on this trip/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("cover-from-phone"));
  await waitFor(async () => expect((await extras.get(TRIP_ID)).cover).not.toBeNull());
  const cover = (await extras.get(TRIP_ID)).cover;
  expect(cover?.uri).toMatch(/^file:\/\/\/app\/covers\/.+\.jpg$/);
  expect(files.kept).toEqual([cover?.uri]);
  await waitFor(() =>
    expect(screen.getAllByTestId("cover-photo")[0]?.props.source).toEqual({ uri: cover?.uri }),
  );
  // It is uploaded for everyone on the trip (ADR 034); the destination photo's credit is gone.
  await waitFor(async () =>
    expect((await extras.get(TRIP_ID)).cover?.serverId).toBe(
      "00000000-0000-4000-8000-0000000c0c01",
    ),
  );
  expect(client.count("PUT /v1/trips/{trip_id}/own-cover")).toBe(1);
  expect(client.count("PUT /v1/trips/{trip_id}/cover")).toBe(0);
  expect(screen.queryByTestId("photo-credit-toggle")).toBeNull();
});

test("a cancelled picker changes nothing", async () => {
  const files = createFakeFiles();
  files.nextImage = null;
  const { extras } = await show({ name: "tripOverview", tripId: TRIP_ID }, { files });
  await screen.findByTestId("day-row-1");
  await fireEvent.press(screen.getByTestId("trip-menu"));
  await fireEvent.press(await screen.findByTestId("menu-change-photo"));
  await fireEvent.press(screen.getByTestId("cover-from-phone"));
  expect(screen.getByTestId("cover-from-phone")).toBeOnTheScreen(); // the sheet stays open
  expect((await extras.get(TRIP_ID)).cover).toBeNull();
});

test("Automatic photo goes back to the destination's photo and deletes the copy", async () => {
  const uri = "file:///app/covers/t-1.jpg";
  const extras = createMemoryExtrasStore([
    withAlbum({ cover: { uri, fileName: "IMG.jpg", setAt: 1 } }),
  ]);
  const { files, client } = await show({ name: "tripOverview", tripId: TRIP_ID }, { extras });
  await screen.findByTestId("day-row-1");
  await waitFor(() =>
    expect(screen.getAllByTestId("cover-photo")[0]?.props.source).toEqual({ uri }),
  );
  await fireEvent.press(screen.getByTestId("trip-menu"));
  await fireEvent.press(await screen.findByTestId("menu-change-photo"));
  expect(screen.getByText(/Your own picture is the cover now/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("cover-automatic"));
  await waitFor(async () => expect((await extras.get(TRIP_ID)).cover).toBeNull());
  expect(files.removed).toEqual([uri]);
  expect(client.count("PUT /v1/trips/{trip_id}/cover")).toBe(1);
  expect(client.count("DELETE /v1/trips/{trip_id}/own-cover")).toBe(1);
  // The albums are untouched.
  expect((await extras.get(TRIP_ID)).albums).toHaveLength(1);
});

test("a picture that can no longer be shown falls back to the destination's photo", async () => {
  const uri = "file:///app/covers/gone.jpg";
  const extras = createMemoryExtrasStore([
    { tripId: TRIP_ID, albums: [], cover: { uri, fileName: "x.jpg", setAt: 1 } },
  ]);
  await show({ name: "tripOverview", tripId: TRIP_ID }, { extras });
  await screen.findByTestId("day-row-1");
  await waitFor(() =>
    expect(screen.getAllByTestId("cover-photo")[0]?.props.source).toEqual({ uri }),
  );
  await fireEvent(screen.getAllByTestId("cover-photo")[0]!, "error", { nativeEvent: {} });
  expect(screen.getAllByTestId("cover-photo")[0]?.props.source.uri).toMatch(
    /^https:\/\/api\.example\.org\/v1\/images\//,
  );
});

test("the trips list shows a trip's own cover", async () => {
  const uri = "file:///app/covers/t-9.jpg";
  await show(
    { name: "trips" },
    {
      extras: createMemoryExtrasStore([
        { tripId: TRIP_ID, albums: [], cover: { uri, fileName: "x.jpg", setAt: 1 } },
      ]),
    },
  );
  await screen.findByTestId(`trip-card-${TRIP_ID}`);
  await waitFor(() =>
    expect(screen.getAllByTestId("cover-photo")[0]?.props.source).toEqual({ uri }),
  );
});

test("deleting a trip deletes its album links and its cover copy", async () => {
  const uri = "file:///app/covers/t-1.jpg";
  const extras = createMemoryExtrasStore([
    withAlbum({ cover: { uri, fileName: "IMG.jpg", setAt: 1 } }),
    { ...withAlbum(), tripId: "another-trip" },
  ]);
  const { files } = await show({ name: "tripSettings", tripId: TRIP_ID }, { extras });
  await fireEvent.press(await screen.findByTestId("delete-trip"));
  await fireEvent.press(screen.getByTestId("confirm-delete"));
  expect(await screen.findByText("No trips yet")).toBeOnTheScreen();
  expect(await extras.get(TRIP_ID)).toEqual(emptyExtras(TRIP_ID));
  expect((await extras.get("another-trip")).albums).toHaveLength(1);
  expect(files.removed).toEqual([uri]);
});

test("a picture from the phone chosen on the new-trip screen becomes the new trip's cover", async () => {
  const stored: unknown[] = [];
  const client = createFakeClient({
    "GET /v1/trips": () => stored,
    "GET /v1/destinations/search": () => ({
      query: "vie",
      external: { state: "not_requested", results: [] },
      results: [makeDestination({ ref: "900101" })],
    }),
    "GET /v1/destinations/{kind}/{ref}/cover-candidates": () => [],
    "POST /v1/trips": () => {
      stored.unshift(makeTrip({ selected_itinerary_id: ESSENTIALS_ID }));
      return makeTrip();
    },
    "POST /v1/trips/{trip_id}/itineraries": () => makeItinerary("essentials"),
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/itineraries": () => [
      makeSummary("essentials", { status: "selected" }),
    ],
    "PATCH /v1/trips/{trip_id}": () => makeTrip({ selected_itinerary_id: ESSENTIALS_ID }),
    ...tripFiles(),
  } as never);
  const { extras, files } = await show({ name: "createTrip" }, { client });
  jest.useFakeTimers();
  await fireEvent.changeText(screen.getByLabelText("Destination"), "Vie");
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS + 10);
  });
  jest.useRealTimers();
  await fireEvent.press(await screen.findByText("Vienna"));
  await fireEvent.press(await screen.findByTestId("change-photo"));
  await fireEvent.press(await screen.findByTestId("cover-from-phone"));
  expect(await screen.findByText("Your photo")).toBeOnTheScreen();
  const staged = files.kept[0];
  expect(staged).toMatch(/^file:\/\/\/app\/covers\/new-/);
  await fireEvent.press(screen.getByText("Start a fresh trip"));
  await screen.findByTestId("trip-cover");
  expect((await extras.get(TRIP_ID)).cover?.uri).toBe(staged);
  expect(files.removed).toEqual([]); // adopted, not thrown away
  expect(client.count("PUT /v1/trips/{trip_id}/cover")).toBe(0);
});

// -- keeping the phone in line with the server (ADR 034, step 5) ---------------------------------

test("an album linked on this phone by an older version is uploaded for the trip", async () => {
  const albums: Album[] = [];
  const local = withAlbum({ albums: [{ id: "album-1", name: "Old", url: ALBUM, createdAt: 1 }] });
  const extras = createMemoryExtrasStore([local]);
  const client = server({}, albums);
  await show(PHOTOS, { extras, client });
  await waitFor(() => expect(albums.map((a) => a.url)).toEqual([ALBUM]));
  await waitFor(async () =>
    expect((await extras.get(TRIP_ID)).albums.map((a) => a.id)).toEqual([albums[0]?.id]),
  );
});

test("a cover chosen on the other phone is downloaded and shown", async () => {
  const COVER = "00000000-0000-4000-8000-0000000c0c09";
  const own = { id: COVER, bytes: 4, uploaded_at: "2026-11-16T10:00:00Z" };
  const client = server({
    "GET /v1/trips": () => [
      makeTrip({ selected_itinerary_id: ESSENTIALS_ID, own_cover: own } as never),
    ],
    "GET /v1/trips/{trip_id}/own-cover": () => ({
      id: COVER,
      content_type: "image/jpeg",
      data: "/9j/4A==",
    }),
  });
  const extras = createMemoryExtrasStore();
  const files = createFakeFiles();
  await show({ name: "trips" }, { extras, files, client });
  await waitFor(async () => expect((await extras.get(TRIP_ID)).cover?.serverId).toBe(COVER));
  const uri = (await extras.get(TRIP_ID)).cover?.uri;
  expect(uri).toMatch(/^file:\/\/\/app\/covers\/.+\.jpg$/);
  await waitFor(() =>
    expect(screen.getAllByTestId("cover-photo")[0]?.props.source).toEqual({ uri }),
  );
  expect(client.count("PUT /v1/trips/{trip_id}/own-cover")).toBe(0);
});
