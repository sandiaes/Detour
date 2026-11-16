import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { AppContent } from "../App";
import { downloadsAhead } from "../documents/DocumentsProvider";
import type { TripDocument } from "../documents/model";
import { createMemoryDocumentStore } from "../documents/store";
import { localToday } from "../domain/trips";
import { createFakeClient } from "../testing/fakeClient";
import { createFakeFiles } from "../testing/fakeFiles";
import { ESSENTIALS_ID, TRIP_ID, makeItinerary, makeTrip } from "../testing/fixtures";
import { Harness } from "../testing/harness";

// Documents shared with everyone on a trip (ADR 034, step 6).

const DOCS = { name: "tripOverview", tripId: TRIP_ID, section: "documents" } as const;
const SHARED_ID = "00000000-0000-4000-8000-0000000d0c01";

type ServerDoc = Record<string, unknown> & { id: string };

function serverDoc(over: Partial<ServerDoc> = {}): ServerDoc {
  return {
    id: SHARED_ID,
    title: "Flight to Lisbon",
    category: "transport",
    link: { kind: "trip" },
    date: null,
    notes: null,
    file_name: "tap.pdf",
    content_type: "application/pdf",
    bytes: 90_000,
    added_by: "Ana",
    created_at: "2026-11-16T10:00:00Z",
    updated_at: "2026-11-16T10:00:00Z",
    ...over,
  };
}

function server(docs: ServerDoc[] = [], handlers: Record<string, unknown> = {}, trip = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID, ...trip })],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "GET /v1/trips/{trip_id}/albums": () => [],
    "GET /v1/trips/{trip_id}/documents": () => docs,
    "POST /v1/trips/{trip_id}/documents": ({ body }: { body: ServerDoc }) => {
      const stored = serverDoc({ ...body, bytes: 4 });
      docs.push(stored);
      return stored;
    },
    "GET /v1/trips/{trip_id}/documents/{document_id}/file": ({
      params,
    }: {
      params: { document_id: string };
    }) => ({ id: params.document_id, content_type: "application/pdf", data: "JVBERi0=" }),
    "DELETE /v1/trips/{trip_id}/documents/{document_id}": ({
      params,
    }: {
      params: { document_id: string };
    }) => {
      const at = docs.findIndex((d) => d.id === params.document_id);
      if (at >= 0) docs.splice(at, 1);
      return undefined;
    },
    ...handlers,
  } as never);
}

function local(over: Partial<TripDocument> = {}): TripDocument {
  return {
    id: "old-doc-1",
    tripId: TRIP_ID,
    title: "Hotel booking",
    category: "booking",
    link: { kind: "trip" },
    fileName: "hotel.pdf",
    mimeType: "application/pdf",
    sizeBytes: 50_000,
    uri: `file:///app/documents/${TRIP_ID}/old-doc-1.pdf`,
    createdAt: 1,
    ...over,
  };
}

async function show(
  initial: Parameters<typeof Harness>[0]["initial"],
  client: ReturnType<typeof server>,
  documents = createMemoryDocumentStore(),
  files = createFakeFiles(),
) {
  await render(
    <Harness client={client} initial={initial} documents={documents} files={files}>
      <AppContent />
    </Harness>,
  );
  return { documents, files };
}

test("a new document is uploaded by default, under the id it has on the phone", async () => {
  const docs: ServerDoc[] = [];
  const client = server(docs);
  const { documents } = await show(DOCS, client);
  await fireEvent.press(await screen.findByTestId("add-document"));
  await fireEvent.press(await screen.findByTestId("choose-file"));
  await fireEvent.press(await screen.findByRole("button", { name: "Ticket" }));
  await fireEvent.press(screen.getByTestId("save-document"));
  expect(
    await screen.findByLabelText("Kept: Shared with the trip, and on this phone"),
  ).toBeOnTheScreen();
  const [doc] = await documents.list(TRIP_ID);
  expect(doc?.serverId).toBe(doc?.id);
  const sent = client.calls.find((c) => c.method === "POST" && c.path.endsWith("/documents"));
  expect(sent?.body).toMatchObject({
    id: doc?.id,
    category: "ticket",
    content_type: "application/pdf",
    data: "/9j/4A==",
  });
});

test("a failed upload keeps the document on the phone and offers to upload it again", async () => {
  let refuse = true;
  const docs: ServerDoc[] = [];
  const client = server(docs, {
    "POST /v1/trips/{trip_id}/documents": ({ body }: { body: ServerDoc }) => {
      if (refuse) return { status: 409, body: { detail: "x", code: "storage_full" } };
      const stored = serverDoc({ ...body, bytes: 4 });
      docs.push(stored);
      return stored;
    },
  });
  const { documents } = await show(DOCS, client);
  await fireEvent.press(await screen.findByTestId("add-document"));
  await fireEvent.press(await screen.findByTestId("choose-file"));
  await fireEvent.press(await screen.findByRole("button", { name: "Ticket" }));
  await fireEvent.press(screen.getByTestId("save-document"));
  expect(await screen.findByLabelText("Kept: On this phone only")).toBeOnTheScreen();
  expect((await documents.list(TRIP_ID))[0]?.serverId ?? null).toBeNull();
  refuse = false;
  await fireEvent.press(screen.getByTestId("share-document"));
  expect(
    await screen.findByLabelText("Kept: Shared with the trip, and on this phone"),
  ).toBeOnTheScreen();
});

test("a document shared by the other person appears, and opening it downloads it", async () => {
  const client = server([serverDoc()]);
  const { documents, files } = await show(DOCS, client);
  expect(await screen.findByText("Flight to Lisbon")).toBeOnTheScreen();
  expect(screen.getByText(/Not downloaded yet/)).toBeOnTheScreen();
  expect(client.count("GET /v1/trips/{trip_id}/documents/{document_id}/file")).toBe(0);
  await fireEvent.press(screen.getByText("Flight to Lisbon"));
  await fireEvent.press(await screen.findByTestId("open-document"));
  await waitFor(() => expect(files.opened).toHaveLength(1));
  expect(client.count("GET /v1/trips/{trip_id}/documents/{document_id}/file")).toBe(1);
  expect((await documents.list(TRIP_ID))[0]?.uri).toMatch(/^file:\/\/\/app\/documents\//);
});

test("a trip that is near has its shared documents downloaded ahead", async () => {
  const client = server([serverDoc()], {}, { start_date: localToday(), end_date: localToday() });
  const { documents } = await show(DOCS, client);
  await waitFor(async () => expect((await documents.list(TRIP_ID))[0]?.uri).toBeTruthy());
});

test("a document deleted on the other phone goes from this one", async () => {
  const gone = local({ id: SHARED_ID, serverId: SHARED_ID });
  const documents = createMemoryDocumentStore([gone]);
  const { files } = await show(DOCS, server([]), documents);
  await waitFor(async () => expect(await documents.list(TRIP_ID)).toEqual([]));
  expect(files.removed).toEqual([gone.uri]);
});

test("documents kept only on this phone can be shared in one tap", async () => {
  const docs: ServerDoc[] = [];
  const documents = createMemoryDocumentStore([local()]);
  await show(DOCS, server(docs), documents);
  expect(await screen.findByText(/1 document is only on this phone/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Share them with the trip"));
  await waitFor(() => expect(docs).toHaveLength(1));
  const [doc] = await documents.list(TRIP_ID);
  // An older identifier is not a UUID: the server copy gets a new one.
  expect(doc?.id).toBe("old-doc-1");
  expect(doc?.serverId).toMatch(/^[0-9a-f-]{36}$/);
});

test("deleting a shared document deletes it for everyone", async () => {
  const docs = [serverDoc()];
  const documents = createMemoryDocumentStore([
    local({ id: SHARED_ID, serverId: SHARED_ID, title: "Flight to Lisbon" }),
  ]);
  await show({ name: "document", tripId: TRIP_ID, documentId: SHARED_ID }, server(docs), documents);
  await fireEvent.press(await screen.findByTestId("delete-document"));
  expect(screen.getByText(/deleted for everyone on this trip/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("confirm-delete-document"));
  await waitFor(() => expect(docs).toEqual([]));
  expect(await documents.list(TRIP_ID)).toEqual([]);
});

test("a shared document can be kept on this phone only", async () => {
  const docs = [serverDoc()];
  const documents = createMemoryDocumentStore([
    local({ id: SHARED_ID, serverId: SHARED_ID, title: "Flight to Lisbon" }),
  ]);
  await show({ name: "document", tripId: TRIP_ID, documentId: SHARED_ID }, server(docs), documents);
  await fireEvent.press(await screen.findByTestId("unshare-document"));
  await fireEvent.press(await screen.findByTestId("confirm-unshare-document"));
  expect(await screen.findByLabelText("Kept: On this phone only")).toBeOnTheScreen();
  expect(docs).toEqual([]);
  expect(await documents.list(TRIP_ID)).toHaveLength(1);
});

test("downloads ahead only for a trip that is near or under way", () => {
  const today = new Date(2027, 4, 1);
  const trip = (start: string | null, end: string | null) =>
    makeTrip({ start_date: start, end_date: end });
  expect(downloadsAhead(trip("2027-05-10", "2027-05-12"), today)).toBe(true);
  expect(downloadsAhead(trip("2027-06-10", "2027-06-12"), today)).toBe(false);
  expect(downloadsAhead(trip("2027-04-28", "2027-05-02"), today)).toBe(true);
  expect(downloadsAhead(trip("2027-04-01", "2027-04-03"), today)).toBe(false);
  expect(downloadsAhead(trip(null, null), today)).toBe(false);
});
