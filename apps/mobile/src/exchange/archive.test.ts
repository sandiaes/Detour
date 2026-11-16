import type { TripFile } from "@detour/shared";
import { strToU8, unzipSync, zipSync } from "fflate";

import {
  ArchiveError,
  MAX_ARCHIVE_BYTES,
  buildArchive,
  describeFile,
  exportFileName,
  readArchive,
} from "./archive";

const trip = (over: Record<string, unknown> = {}) => ({
  title: "Hallstatt",
  destination: { kind: "place", ref: "photon:N1", name: "Hallstatt", lat: 47.56, lon: 13.64 },
  duration_days: 2,
  status: "active",
  stops: [],
  visits: [],
  days: [
    {
      day_index: 1,
      items: [
        { position: 1, kind: "place", name: "Church", lat: 1, lon: 1, duration_minutes: 30 },
        { position: 2, kind: "cafe", name: "Seecafe", lat: 1, lon: 1, duration_minutes: 45 },
      ],
    },
  ],
  ...over,
});

const file = (trips: unknown[] = [trip()], over: Record<string, unknown> = {}): TripFile =>
  ({ format: "detour-trip", format_version: 1, trips, ...over }) as unknown as TripFile;

const pdf = new Uint8Array([37, 80, 68, 70, 1, 2, 3]);

const doc = (over = {}) => ({
  tripIndex: 0,
  title: "Train to Graz",
  category: "transport" as const,
  link: { kind: "place" as const, name: "Church", day: 1 },
  date: "2027-05-02",
  notes: "Seat 12A",
  fileName: "oebb.pdf",
  mimeType: "application/pdf",
  bytes: pdf,
  ...over,
});

test("a file with documents reads back as it was written", () => {
  const read = readArchive(buildArchive(file(), [doc()]));
  expect(read.file.trips[0]?.title).toBe("Hallstatt");
  expect(read.skipped).toEqual([]);
  expect(read.documents).toHaveLength(1);
  const d = read.documents[0];
  expect(d).toMatchObject({
    tripIndex: 0,
    title: "Train to Graz",
    category: "transport",
    link: { kind: "place", name: "Church", day: 1 },
    date: "2027-05-02",
    notes: "Seat 12A",
    fileName: "oebb.pdf",
    mimeType: "application/pdf",
  });
  expect(Array.from(d?.bytes ?? [])).toEqual(Array.from(pdf));
});

test("without documents the zip holds only trip.json, readable with any zip tool", () => {
  const entries = unzipSync(buildArchive(file(), []));
  expect(Object.keys(entries)).toEqual(["trip.json"]);
  expect(JSON.parse(new TextDecoder().decode(entries["trip.json"])).format).toBe("detour-trip");
});

test("documents are stored under generated names, never the user's file names", () => {
  const entries = unzipSync(
    buildArchive(file(), [doc({ fileName: "../../etc/Passport copy.PDF" })]),
  );
  expect(Object.keys(entries).sort()).toEqual(["documents.json", "documents/1.pdf", "trip.json"]);
});

test.each([
  ["not a zip", new Uint8Array([1, 2, 3, 4])],
  ["a zip without trip.json", zipSync({ "other.txt": strToU8("x") })],
  [
    "a zip of another format",
    zipSync({ "trip.json": strToU8(JSON.stringify({ format: "x", trips: [] })) }),
  ],
  ["damaged json", zipSync({ "trip.json": strToU8("{oops") })],
  [
    "no version",
    zipSync({ "trip.json": strToU8(JSON.stringify({ format: "detour-trip", trips: [] })) }),
  ],
])("%s is refused in words", (_name, bytes) => {
  expect(() => readArchive(bytes)).toThrow(ArchiveError);
});

test("a newer format is refused with a request to update", () => {
  const bytes = zipSync({ "trip.json": strToU8(JSON.stringify(file([], { format_version: 2 }))) });
  expect(() => readArchive(bytes)).toThrow(/newer version of Detour/);
});

test("a file over 50 MB is refused before it is unpacked", () => {
  expect(() => readArchive(new Uint8Array(MAX_ARCHIVE_BYTES + 1))).toThrow(/50 MB/);
});

test("a document that is missing, mislinked or outside documents/ is skipped, the trip still opens", () => {
  const good = buildArchive(file(), [doc({ title: "Good" })]);
  const entries = unzipSync(good);
  const list = JSON.parse(new TextDecoder().decode(entries["documents.json"]));
  const base = list.documents[0];
  list.documents = [
    base,
    { ...base, title: "Missing", path: "documents/9.pdf" },
    { ...base, title: "Escapes", path: "../trip.json" },
    { ...base, title: "Other trip", trip_index: 4 },
    { ...base, title: "Bad link", link: { kind: "place" } },
  ];
  entries["documents.json"] = strToU8(JSON.stringify(list));
  const read = readArchive(zipSync(entries));
  expect(read.documents.map((d) => d.title)).toEqual(["Good"]);
  expect(read.skipped).toEqual(["Missing", "Escapes", "Other trip", "Bad link"]);
});

test("an unknown document kind reads as other", () => {
  const entries = unzipSync(buildArchive(file(), [doc()]));
  const list = JSON.parse(new TextDecoder().decode(entries["documents.json"]));
  list.documents[0].category = "insurance";
  entries["documents.json"] = strToU8(JSON.stringify(list));
  expect(readArchive(zipSync(entries)).documents[0]?.category).toBe("other");
});

test("the preview counts stops of a plan and visits of a past trip", () => {
  const read = readArchive(
    buildArchive(
      file([
        trip(),
        trip({
          title: "Old",
          status: "past",
          days: [],
          visits: [{ kind: "attraction", name: "X", lat: 1, lon: 1, day_number: 1 }],
        }),
      ]),
      [doc()],
    ),
  );
  expect(describeFile(read)).toEqual({
    trips: [
      { title: "Hallstatt", destination: "Hallstatt", days: 2, stops: 2, past: false },
      { title: "Old", destination: "Hallstatt", days: 2, stops: 1, past: true },
    ],
    documents: 1,
    albums: 0,
  });
});

test("the shared file's name is safe and dated", () => {
  const day = new Date("2026-11-14T10:00:00Z");
  expect(exportFileName("Zürich & Lucerne / 2027", day)).toBe(
    "Detour-Zurich-Lucerne-2027-2026-11-14.detour",
  );
  expect(exportFileName(null, day)).toBe("Detour-backup-2026-11-14.detour");
  expect(exportFileName("日本", day)).toBe("Detour-trip-2026-11-14.detour");
});

test("album links travel in albums.json; a link that is not https or names no trip is dropped", () => {
  const bytes = buildArchive(
    file(),
    [],
    [{ tripIndex: 0, name: "Rome with Ana", url: "https://photos.app.goo.gl/r" }],
  );
  const zip = unzipSync(bytes);
  expect(Object.keys(zip).sort()).toEqual(["albums.json", "trip.json"]);
  expect(readArchive(bytes).albums).toEqual([
    { tripIndex: 0, name: "Rome with Ana", url: "https://photos.app.goo.gl/r" },
  ]);
  const hand = zipSync({
    "trip.json": zip["trip.json"] as Uint8Array,
    "albums.json": strToU8(
      JSON.stringify({
        albums: [
          { trip_index: 0, name: "", url: "https://photos.app.goo.gl/ok" },
          { trip_index: 0, name: "Bad", url: "javascript:alert(1)" },
          { trip_index: 3, name: "Nowhere", url: "https://photos.app.goo.gl/x" },
        ],
      }),
    ),
  });
  const read = readArchive(hand);
  expect(read.albums).toEqual([
    { tripIndex: 0, name: "Trip album", url: "https://photos.app.goo.gl/ok" },
  ]);
  expect(describeFile(read).albums).toBe(1);
  // A file without albums has none.
  expect(readArchive(buildArchive(file(), [])).albums).toEqual([]);
});
