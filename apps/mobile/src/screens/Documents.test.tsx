import { fireEvent, render, screen } from "@testing-library/react-native";

import { AppContent } from "../App";
import type { TripDocument } from "../documents/model";
import { createMemoryDocumentStore } from "../documents/store";
import { createFakeClient } from "../testing/fakeClient";
import { PICKED_PDF, createFakeFiles } from "../testing/fakeFiles";
import {
  ESSENTIALS_ID,
  TRIP_ID,
  makeArchiveInfo,
  makeArchivedVisits,
  makeItinerary,
  makePastTrip,
  makeTrip,
} from "../testing/fixtures";
import { Harness } from "../testing/harness";

const DOCS = { name: "tripOverview", tripId: TRIP_ID, section: "documents" } as const;

function server(handlers: Record<string, unknown> = {}) {
  return createFakeClient({
    "GET /v1/trips": () => [makeTrip({ selected_itinerary_id: ESSENTIALS_ID })],
    "GET /v1/itineraries/{itinerary_id}": () => makeItinerary("essentials", { status: "selected" }),
    "DELETE /v1/trips/{trip_id}": () => undefined,
    ...handlers,
  } as never);
}

function saved(over: Partial<TripDocument> = {}): TripDocument {
  return {
    id: "doc-1",
    tripId: TRIP_ID,
    title: "Train to Graz",
    category: "transport",
    link: { kind: "leg", day: 2, name: "Graz" },
    fileName: "oebb.pdf",
    mimeType: "application/pdf",
    sizeBytes: 120_000,
    uri: `file:///app/documents/${TRIP_ID}/doc-1.pdf`,
    createdAt: Date.UTC(2027, 3, 20),
    ...over,
  };
}

async function show(
  initial: Parameters<typeof Harness>[0]["initial"],
  {
    documents = createMemoryDocumentStore(),
    files = createFakeFiles(),
    client = server(),
  }: {
    documents?: ReturnType<typeof createMemoryDocumentStore>;
    files?: ReturnType<typeof createFakeFiles>;
    client?: ReturnType<typeof server>;
  } = {},
) {
  await render(
    <Harness client={client} initial={initial} documents={documents} files={files}>
      <AppContent />
    </Harness>,
  );
  return { documents, files, client };
}

test("add a ticket for a place: pick, title from the file, kind, place; it is kept on the phone", async () => {
  const { documents, files } = await show(DOCS);
  await fireEvent.press(await screen.findByTestId("add-document"));
  expect(await screen.findByRole("header", { name: "Add a document" })).toBeOnTheScreen();
  expect(screen.getByTestId("save-document")).toBeDisabled();

  await fireEvent.press(screen.getByTestId("choose-file"));
  expect(await screen.findByText("Train_ticket-Vienna.pdf")).toBeOnTheScreen();
  expect(screen.getByText("PDF · 245.0 kB")).toBeOnTheScreen();
  expect(screen.getByLabelText("Title").props.value).toBe("Train ticket Vienna");
  // A kind is needed before saving.
  expect(screen.getByTestId("save-document")).toBeDisabled();
  await fireEvent.press(screen.getByRole("button", { name: "Ticket" }));
  await fireEvent.press(screen.getByTestId("link-place"));
  // A place must be chosen once "A place" is.
  expect(screen.getByTestId("save-document")).toBeDisabled();
  await fireEvent.press(screen.getByRole("button", { name: "Schönbrunn Palace, Day 1" }));
  await fireEvent.press(screen.getByTestId("save-document"));

  // The document opens; the file was copied into the app's storage.
  expect(await screen.findByRole("header", { name: "Train ticket Vienna" })).toBeOnTheScreen();
  expect(screen.getByLabelText("About: Schönbrunn Palace · day 1")).toBeOnTheScreen();
  expect(files.kept).toHaveLength(1);
  expect(files.kept[0]).toMatch(new RegExp(`^file:///app/documents/${TRIP_ID}/.+\\.pdf$`));
  const [stored] = await documents.list(TRIP_ID);
  expect(stored).toMatchObject({
    title: "Train ticket Vienna",
    category: "ticket",
    link: { kind: "place", key: "name:Schönbrunn Palace", name: "Schönbrunn Palace", day: 1 },
    fileName: PICKED_PDF.name,
    mimeType: "application/pdf",
    sizeBytes: 245_000,
    uri: files.kept[0],
  });

  // Back on the trip, the list has it under Tickets.
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText("Tickets (1)")).toBeOnTheScreen();
  expect(
    screen.getByRole("button", {
      name: "Train ticket Vienna. Schönbrunn Palace · day 1 · PDF · 245.0 kB",
    }),
  ).toBeOnTheScreen();
});

test("a cancelled picker changes nothing; a file that is not a PDF or picture is refused", async () => {
  const files = createFakeFiles(null);
  await show({ name: "documentForm", tripId: TRIP_ID }, { files });
  await fireEvent.press(await screen.findByTestId("choose-file"));
  expect(screen.getByTestId("choose-file")).toBeOnTheScreen();
  files.next = { uri: "content://x/a.zip", name: "a.zip", mimeType: "application/zip", size: 9 };
  await fireEvent.press(screen.getByTestId("choose-file"));
  expect(await screen.findByText(/Detour keeps PDFs and pictures/)).toBeOnTheScreen();
  expect(files.kept).toEqual([]);
});

test("a day, the whole trip or the journey to a new base city can be chosen", async () => {
  const { documents } = await show({ name: "documentForm", tripId: TRIP_ID });
  await fireEvent.press(await screen.findByTestId("choose-file"));
  await fireEvent.press(screen.getByRole("button", { name: "Transport" }));
  // The fixture plan moves to Graz on day 2: that journey can be chosen.
  await fireEvent.press(screen.getByTestId("link-leg"));
  await fireEvent.press(screen.getByRole("button", { name: "To Graz, Day 2 · from Vienna" }));
  await fireEvent.press(screen.getByTestId("save-document"));
  expect(await screen.findByLabelText("About: Journey to Graz · day 2")).toBeOnTheScreen();
  expect((await documents.list(TRIP_ID))[0]?.link).toEqual({ kind: "leg", day: 2, name: "Graz" });
});

test("open, edit and delete a document", async () => {
  const documents = createMemoryDocumentStore([saved()]);
  const files = createFakeFiles();
  await show({ name: "document", tripId: TRIP_ID, documentId: "doc-1" }, { documents, files });
  expect(await screen.findByRole("header", { name: "Train to Graz" })).toBeOnTheScreen();
  expect(screen.getByLabelText("About: Journey to Graz · day 2")).toBeOnTheScreen();
  expect(screen.getByLabelText("Type and size: PDF · 120.0 kB")).toBeOnTheScreen();

  await fireEvent.press(screen.getByTestId("open-document"));
  expect(files.opened).toEqual([saved().uri]);
  files.openFails = "No app on this device can show this kind of file.";
  await fireEvent.press(screen.getByTestId("open-document"));
  expect(await screen.findByText(/No app on this device can show/)).toBeOnTheScreen();

  // Edit: a new title and a day instead of the journey; the file stays.
  await fireEvent.press(screen.getByTestId("edit-document"));
  expect(await screen.findByRole("header", { name: "Edit document" })).toBeOnTheScreen();
  expect(screen.queryByTestId("choose-file")).toBeNull();
  await fireEvent.changeText(screen.getByLabelText("Title"), "ÖBB train, day 2");
  await fireEvent.press(screen.getByTestId("link-day"));
  await fireEvent.press(screen.getByRole("button", { name: "Day 2 · Sun 2 May" }));
  await fireEvent.press(screen.getByTestId("save-document"));
  expect(await screen.findByRole("header", { name: "ÖBB train, day 2" })).toBeOnTheScreen();
  expect(screen.getByLabelText("About: Day 2 · Sun 2 May")).toBeOnTheScreen();

  // Delete asks first, then removes the entry and its file.
  await fireEvent.press(screen.getByTestId("delete-document"));
  expect(screen.getByText(/will be removed from this phone/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("confirm-delete-document"));
  expect(await documents.get("doc-1")).toBeNull();
  expect(files.removed).toEqual([saved().uri]);
});

test("a place shows only its own documents, and a new one starts linked to it", async () => {
  const documents = createMemoryDocumentStore([
    saved({
      id: "t1",
      title: "Palace tickets",
      category: "ticket",
      link: { kind: "place", key: "name:Schönbrunn Palace", name: "Schönbrunn Palace", day: 1 },
    }),
    saved({ id: "t2", title: "Insurance", category: "insurance", link: { kind: "trip" } }),
  ]);
  await show(
    { name: "placeDetail", tripId: TRIP_ID, itineraryId: ESSENTIALS_ID, itemId: "i1" },
    { documents },
  );
  expect(await screen.findByText("Tickets and documents")).toBeOnTheScreen();
  expect(await screen.findByText("Palace tickets")).toBeOnTheScreen();
  expect(screen.queryByText("Insurance")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Attach a document" }));
  expect(await screen.findByRole("header", { name: "Add a document" })).toBeOnTheScreen();
  expect(screen.getByTestId("link-place").props.accessibilityState).toMatchObject({
    selected: true,
  });
  expect(
    screen.getByRole("button", { name: "Schönbrunn Palace, Day 1" }).props.accessibilityState,
  ).toMatchObject({ selected: true });
});

test("Add on a trip offers a document", async () => {
  await show({ name: "tripOverview", tripId: TRIP_ID });
  await screen.findByRole("header", { name: "Your itinerary" });
  await fireEvent.press(screen.getByRole("button", { name: "Add to this trip" }));
  await fireEvent.press(await screen.findByTestId("add-sheet-document"));
  expect(await screen.findByRole("header", { name: "Add a document" })).toBeOnTheScreen();
});

test("deleting a trip deletes its documents and their files, and no other trip's", async () => {
  const documents = createMemoryDocumentStore([
    saved(),
    saved({ id: "other", tripId: "another-trip", uri: "file:///other.pdf" }),
  ]);
  const files = createFakeFiles();
  await show({ name: "tripSettings", tripId: TRIP_ID }, { documents, files });
  expect(await screen.findByText(/its documents on this phone/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("delete-trip"));
  await fireEvent.press(screen.getByTestId("confirm-delete"));
  expect(await screen.findByText("No trips yet")).toBeOnTheScreen();
  expect(await documents.list(TRIP_ID)).toEqual([]);
  expect(await documents.list("another-trip")).toHaveLength(1);
  expect(files.removed).toEqual([saved().uri]);
});

test("a past trip keeps its documents, reached from its screen", async () => {
  const documents = createMemoryDocumentStore([
    saved({ title: "Hotel booking", category: "booking", link: { kind: "trip" } }),
  ]);
  await show(
    { name: "pastTrip", tripId: TRIP_ID },
    {
      documents,
      client: createFakeClient({
        "GET /v1/trips": () => [makePastTrip()],
        "GET /v1/trips/{trip_id}/visits": () => makeArchivedVisits(),
        "GET /v1/trips/{trip_id}/archive": () => makeArchiveInfo(),
      }),
    },
  );
  await fireEvent.press(await screen.findByTestId("past-trip-documents"));
  expect(await screen.findByRole("header", { name: "Documents" })).toBeOnTheScreen();
  expect(await screen.findByText("Bookings (1)")).toBeOnTheScreen();
  expect(screen.getByText("Hotel booking")).toBeOnTheScreen();
});
