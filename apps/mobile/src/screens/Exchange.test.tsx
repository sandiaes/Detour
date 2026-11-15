import type { TripFile } from "@detour/shared";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { unzipSync } from "fflate";

import { AppContent, isTripFileLink } from "../App";
import type { TripDocument } from "../documents/model";
import { createMemoryDocumentStore } from "../documents/store";
import { buildArchive } from "../exchange/archive";
import { createFakeClient } from "../testing/fakeClient";
import { createFakeExchange } from "../testing/fakeFiles";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

const NEW_TRIP = "00000000-0000-4000-8000-0000000000b9";

const fileTrip = (over: Record<string, unknown> = {}) => ({
  title: "Vienna",
  destination: { kind: "place", ref: "geonames:900101", name: "Vienna", lat: 48.2, lon: 16.37 },
  duration_days: 2,
  status: "active",
  stops: [],
  visits: [],
  days: [
    {
      day_index: 1,
      items: [
        {
          position: 1,
          kind: "sight",
          name: "Schönbrunn Palace",
          lat: 48.18,
          lon: 16.31,
          duration_minutes: 120,
        },
      ],
    },
  ],
  ...over,
});

const tripFile = (trips: unknown[] = [fileTrip()]): TripFile =>
  ({ format: "detour-trip", format_version: 1, trips }) as unknown as TripFile;

const saved = (over: Partial<TripDocument> = {}): TripDocument => ({
  id: "doc-1",
  tripId: TRIP_ID,
  title: "Train to Graz",
  category: "transport",
  link: { kind: "place", key: "name:Schönbrunn Palace", name: "Schönbrunn Palace", day: 1 },
  fileName: "oebb.pdf",
  mimeType: "application/pdf",
  sizeBytes: 3,
  uri: `file:///app/documents/${TRIP_ID}/doc-1.pdf`,
  createdAt: Date.UTC(2027, 3, 20),
  date: "2027-05-02",
  notes: "Seat 12A",
  ...over,
});

function server(handlers: Record<string, unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip(), makeTrip({ id: "second", title: "Graz" })],
    "GET /v1/trips/{trip_id}/export": ({ params }: { params: { trip_id: string } }) =>
      tripFile([fileTrip({ title: params.trip_id === TRIP_ID ? "Vienna" : "Graz" })]),
    "POST /v1/trips/import": () => ({
      trips: [{ index: 0, trip_id: NEW_TRIP, title: "Vienna", days: 1, stops: 1 }],
    }),
    "GET /v1/trips/{trip_id}": () =>
      makeTrip({ id: NEW_TRIP, selected_itinerary_id: ESSENTIALS_ID, duration_days: 2 }),
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    ...handlers,
  } as never);
}

async function show(
  initial: Parameters<typeof Harness>[0]["initial"],
  opts: {
    documents?: ReturnType<typeof createMemoryDocumentStore>;
    exchange?: ReturnType<typeof createFakeExchange>;
    client?: ReturnType<typeof server>;
  } = {},
) {
  const documents = opts.documents ?? createMemoryDocumentStore();
  const exchange = opts.exchange ?? createFakeExchange();
  const client = opts.client ?? server();
  await render(
    <Harness client={client} initial={initial} documents={documents} exchange={exchange}>
      <AppContent />
    </Harness>,
  );
  return { documents, exchange, client };
}

function sharedZip(exchange: ReturnType<typeof createFakeExchange>) {
  const uri = exchange.shared[0]?.uri ?? "";
  return unzipSync(exchange.disk.get(uri) ?? new Uint8Array());
}

// -- export ------------------------------------------------------------------------------------

test("exporting a trip with documents shares one file holding both, after a plain warning", async () => {
  const exchange = createFakeExchange();
  const doc = saved();
  exchange.disk.set(doc.uri, new Uint8Array([37, 80, 68, 70]));
  const { client } = await show(
    { name: "exportTrips", tripId: TRIP_ID },
    { documents: createMemoryDocumentStore([doc]), exchange },
  );
  expect(await screen.findByText(/Include documents \(3 bytes\)/)).toBeTruthy();
  expect(screen.getByText(/not encrypted/)).toBeTruthy();
  await fireEvent.press(screen.getByTestId("export-run"));
  await screen.findByText(/holds 1 trip and 1 document/);
  expect(exchange.shared).toHaveLength(1);
  expect(exchange.shared[0]?.name).toMatch(/^Detour-Vienna-\d{4}-\d\d-\d\d\.detour$/);
  const zip = sharedZip(exchange);
  expect(Object.keys(zip).sort()).toEqual(["documents.json", "documents/1.pdf", "trip.json"]);
  expect(Array.from(zip["documents/1.pdf"] ?? [])).toEqual([37, 80, 68, 70]);
  const list = JSON.parse(new TextDecoder().decode(zip["documents.json"]));
  // The link names the place; the device's own identifier does not leave the phone.
  expect(list.documents[0].link).toEqual({ kind: "place", name: "Schönbrunn Palace", day: 1 });
  expect(client.count("GET /v1/trips/{trip_id}/export")).toBe(1);
});

test("with the switch off the file holds no documents", async () => {
  const exchange = createFakeExchange();
  const doc = saved();
  exchange.disk.set(doc.uri, new Uint8Array([1]));
  await show(
    { name: "exportTrips", tripId: TRIP_ID },
    { documents: createMemoryDocumentStore([doc]), exchange },
  );
  await fireEvent(await screen.findByTestId("include-documents"), "valueChange", false);
  expect(screen.queryByText(/not encrypted/)).toBeNull();
  await fireEvent.press(screen.getByTestId("export-run"));
  await screen.findByText(/holds 1 trip\./);
  expect(Object.keys(sharedZip(exchange))).toEqual(["trip.json"]);
});

test("a document whose file is gone is left out and named", async () => {
  const exchange = createFakeExchange(); // the file was never put on the fake disk
  await show(
    { name: "exportTrips", tripId: TRIP_ID },
    { documents: createMemoryDocumentStore([saved()]), exchange },
  );
  await fireEvent.press(await screen.findByTestId("export-run"));
  await screen.findByText(
    /Left out because they could not be read or are too large: Train to Graz/,
  );
  expect(Object.keys(sharedZip(exchange))).toEqual(["trip.json"]);
});

test("a trip with no documents offers no switch", async () => {
  await show({ name: "exportTrips", tripId: TRIP_ID });
  await screen.findByTestId("export-run");
  expect(screen.queryByTestId("include-documents")).toBeNull();
});

test("a backup holds every trip, oldest first, and says when the phone cannot share", async () => {
  const exchange = createFakeExchange();
  exchange.canShare = false;
  const { client } = await show({ name: "exportTrips" }, { exchange });
  await fireEvent.press(await screen.findByTestId("export-run"));
  await screen.findByText(/holds 2 trips/);
  expect(screen.getByText(/no way to share it/)).toBeTruthy();
  expect(
    client.calls.filter((c) => c.path.endsWith("/export")).map((c) => c.params.trip_id),
  ).toEqual(["second", TRIP_ID]);
  const uri = [...exchange.disk.keys()][0] ?? "";
  const file = JSON.parse(
    new TextDecoder().decode(unzipSync(exchange.disk.get(uri) ?? new Uint8Array())["trip.json"]),
  );
  expect(file.trips.map((t: { title: string }) => t.title)).toEqual(["Graz", "Vienna"]);
});

test("More offers the backup and the import", async () => {
  await show({ name: "more" });
  expect(await screen.findByTestId("more-import")).toBeTruthy();
  await fireEvent.press(screen.getByTestId("more-backup"));
  expect(await screen.findByTestId("export-run")).toBeTruthy();
});

test("a trip's menu offers its export", async () => {
  const client = server({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
  });
  await show({ name: "tripOverview", tripId: TRIP_ID }, { client });
  await fireEvent.press((await screen.findAllByTestId("trip-menu"))[0] as never);
  await fireEvent.press(await screen.findByTestId("menu-export"));
  expect(await screen.findByTestId("export-run")).toBeTruthy();
  expect(screen.getByText("Export trip")).toBeTruthy();
});

// -- import ------------------------------------------------------------------------------------

function pickFile(exchange: ReturnType<typeof createFakeExchange>, bytes: Uint8Array) {
  exchange.disk.set("content://picked/trip.detour", bytes);
  exchange.next = { uri: "content://picked/trip.detour", name: "trip.detour" };
}

test("choose a file, see what it holds, import it, and its documents come back linked", async () => {
  const exchange = createFakeExchange();
  pickFile(
    exchange,
    buildArchive(tripFile(), [
      {
        tripIndex: 0,
        title: "Palace ticket",
        category: "ticket",
        link: { kind: "place", name: "Schönbrunn Palace", day: 1 },
        date: null,
        notes: null,
        fileName: "ticket.pdf",
        mimeType: "application/pdf",
        bytes: new Uint8Array([1, 2, 3]),
      },
      {
        tripIndex: 0,
        title: "Late train",
        category: "transport",
        link: { kind: "leg", day: 9, name: "Graz" },
        date: null,
        notes: "Seat 12A",
        fileName: "train.pdf",
        mimeType: "application/pdf",
        bytes: new Uint8Array([4]),
      },
    ]),
  );
  const documents = createMemoryDocumentStore();
  const { client } = await show({ name: "importTrips" }, { documents, exchange });
  await fireEvent.press(await screen.findByTestId("import-choose"));
  expect(await screen.findByText("Vienna")).toBeTruthy();
  expect(screen.getByText(/Vienna · 2 days · 1 stop/)).toBeTruthy();
  expect(screen.getByText(/2 documents come with the trips/)).toBeTruthy();
  expect(client.count("POST /v1/trips/import")).toBe(0); // nothing is written before the user confirms
  await fireEvent.press(screen.getByTestId("import-run"));
  await screen.findByText(/1 trip added with 2 documents/);
  expect(client.count("POST /v1/trips/import")).toBe(1);
  expect(
    (client.calls.find((c) => c.path === "/v1/trips/import")?.body as TripFile).trips,
  ).toHaveLength(1);

  const kept = await documents.list(NEW_TRIP);
  const byTitle = Object.fromEntries(kept.map((d) => [d.title, d]));
  expect(byTitle["Palace ticket"]?.link).toMatchObject({
    kind: "place",
    name: "Schönbrunn Palace",
    day: 1,
  });
  expect(byTitle["Palace ticket"]?.link).toHaveProperty("key");
  expect(byTitle["Late train"]?.link).toEqual({ kind: "trip" }); // day 9 is beyond a 2-day trip
  expect(byTitle["Late train"]?.notes).toBe("Seat 12A");
  expect(byTitle["Palace ticket"]?.uri).toContain(NEW_TRIP);
  expect(exchange.disk.get(byTitle["Palace ticket"]?.uri ?? "")).toEqual(new Uint8Array([1, 2, 3]));
  await fireEvent.press(screen.getByTestId("import-open"));
});

test("a file that is not a trip file says so and imports nothing", async () => {
  const exchange = createFakeExchange();
  pickFile(exchange, new Uint8Array([1, 2, 3]));
  const { client } = await show({ name: "importTrips" }, { exchange });
  await fireEvent.press(await screen.findByTestId("import-choose"));
  expect(await screen.findByText(/This is not a Detour trip file/)).toBeTruthy();
  expect(screen.queryByTestId("import-run")).toBeNull();
  expect(client.count("POST /v1/trips/import")).toBe(0);
});

test("a cancelled picker changes nothing", async () => {
  const exchange = createFakeExchange();
  await show({ name: "importTrips" }, { exchange });
  await fireEvent.press(await screen.findByTestId("import-choose"));
  expect(screen.queryByTestId("import-run")).toBeNull();
  expect(screen.queryByText(/not a Detour/)).toBeNull();
});

test("opening a trip file with the app goes straight to what it holds", async () => {
  const exchange = createFakeExchange();
  exchange.disk.set("content://mail/attachment/9", buildArchive(tripFile(), []));
  await show({ name: "importTrips", uri: "content://mail/attachment/9" }, { exchange });
  expect(await screen.findByText("Vienna")).toBeTruthy();
  expect(screen.getByText(/No documents are in this file/)).toBeTruthy();
});

test("a document that cannot be written is listed; the trip is kept", async () => {
  const exchange = createFakeExchange();
  pickFile(
    exchange,
    buildArchive(tripFile(), [
      {
        tripIndex: 0,
        title: "Ticket",
        category: "ticket",
        link: { kind: "trip" },
        date: null,
        notes: null,
        fileName: "t.pdf",
        mimeType: "application/pdf",
        bytes: new Uint8Array([1]),
      },
    ]),
  );
  exchange.keepBytes = async () => {
    throw new Error("disk full");
  };
  const documents = createMemoryDocumentStore();
  await show({ name: "importTrips" }, { documents, exchange });
  await fireEvent.press(await screen.findByTestId("import-choose"));
  await fireEvent.press(await screen.findByTestId("import-run"));
  expect(await screen.findByText(/1 trip added\./)).toBeTruthy();
  expect(screen.getByText(/could not be restored: Ticket/)).toBeTruthy();
  expect(await documents.list(NEW_TRIP)).toEqual([]);
});

test("the server's refusal of a file is shown and nothing is claimed as imported", async () => {
  const exchange = createFakeExchange();
  pickFile(exchange, buildArchive(tripFile(), []));
  const client = server({
    "POST /v1/trips/import": () => ({
      status: 422,
      body: { code: "bad_file", detail: "trip 1: a day is beyond the trip's length" },
    }),
  });
  await show({ name: "importTrips" }, { exchange, client });
  await fireEvent.press(await screen.findByTestId("import-choose"));
  await fireEvent.press(await screen.findByTestId("import-run"));
  await waitFor(() => expect(screen.getByText(/a day is beyond the trip's length/)).toBeTruthy());
  expect(screen.queryByText(/added/)).toBeNull();
});

test("only a content or file link is taken for a trip file", () => {
  expect(isTripFileLink("content://mail/attachment/9")).toBe(true);
  expect(isTripFileLink("file:///sdcard/Download/a.detour")).toBe(true);
  expect(isTripFileLink("https://example.org/a.detour")).toBe(false);
  expect(isTripFileLink(null)).toBe(false);
  expect(isTripFileLink(undefined)).toBe(false);
});
