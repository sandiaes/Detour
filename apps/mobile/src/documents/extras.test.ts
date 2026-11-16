import {
  type TripExtras,
  albumSource,
  createMemoryExtrasStore,
  createSqliteExtrasStore,
  emptyExtras,
  isGooglePhotos,
  normaliseAlbumUrl,
  sanitiseExtras,
} from "./extras";
import type { DocumentDatabase } from "./store";

// Album links and covers from the phone (ADR 031).

test("an album link is taken from what the user pastes, and only an https address is kept", () => {
  expect(normaliseAlbumUrl("https://photos.app.goo.gl/AbC123")).toBe(
    "https://photos.app.goo.gl/AbC123",
  );
  // Google Photos' share message has words around the link.
  expect(normaliseAlbumUrl("Check out our album: https://photos.app.goo.gl/AbC123. See you!")).toBe(
    "https://photos.app.goo.gl/AbC123",
  );
  expect(normaliseAlbumUrl("  photos.app.goo.gl/AbC123  ")).toBe(
    "https://photos.app.goo.gl/AbC123",
  );
  expect(normaliseAlbumUrl("https://photos.google.com/share/AF1Qip?key=xyz")).toBe(
    "https://photos.google.com/share/AF1Qip?key=xyz",
  );
  for (const bad of [
    "",
    "   ",
    "our album",
    "http://photos.app.goo.gl/AbC123", // not https
    "javascript:alert(1)",
    "file:///sdcard/a.jpg",
    "content://media/external/images/1",
    `https://example.org/${"a".repeat(2100)}`,
  ]) {
    expect(normaliseAlbumUrl(bad)).toBeNull();
  }
});

test("Google Photos links are named as such; other sites by their address", () => {
  expect(isGooglePhotos("https://photos.app.goo.gl/AbC")).toBe(true);
  expect(isGooglePhotos("https://photos.google.com/share/X")).toBe(true);
  expect(isGooglePhotos("https://goo.gl/photos/X")).toBe(true);
  expect(isGooglePhotos("https://goo.gl/maps/X")).toBe(false);
  expect(isGooglePhotos("https://photos.google.com.evil.example/X")).toBe(false);
  expect(albumSource("https://photos.app.goo.gl/AbC")).toBe("Google Photos");
  expect(albumSource("https://www.icloud.com/sharedalbum/#B0")).toBe("icloud.com");
});

test("a damaged or hand-made row is read safely", () => {
  expect(sanitiseExtras("t", null)).toEqual(emptyExtras("t"));
  expect(sanitiseExtras("t", "nonsense")).toEqual(emptyExtras("t"));
  const read = sanitiseExtras("t", {
    albums: [
      { id: "a", name: "  ", url: "https://photos.app.goo.gl/x", createdAt: 5 },
      { id: "b", name: "Bad", url: "javascript:alert(1)" },
      "junk",
    ],
    cover: { uri: "file:///app/covers/t-1.jpg" },
  });
  expect(read.albums).toEqual([
    { id: "a", name: "Trip album", url: "https://photos.app.goo.gl/x", createdAt: 5 },
  ]);
  expect(read.cover).toEqual({ uri: "file:///app/covers/t-1.jpg", fileName: "photo", setAt: 0 });
});

function fakeDatabase(): DocumentDatabase & { rows: Map<string, string> } {
  const rows = new Map<string, string>();
  return {
    rows,
    execAsync: async () => undefined,
    getFirstAsync: async <T>(_s: string, ...p: (string | number)[]) =>
      (rows.has(String(p[0])) ? { json: rows.get(String(p[0])) } : null) as T | null,
    getAllAsync: async <T>() =>
      [...rows.entries()].map(([trip_id, json]) => ({ trip_id, json })) as T[],
    runAsync: async (s, ...p) => {
      if (s.startsWith("INSERT")) rows.set(String(p[0]), String(p[1]));
      if (s.startsWith("DELETE")) rows.delete(String(p[0]));
    },
  };
}

describe.each([
  ["memory", () => createMemoryExtrasStore()],
  ["sqlite", () => createSqliteExtrasStore(async () => fakeDatabase())],
])("the %s extras store", (_name, make) => {
  test("keeps each trip's albums and cover apart, and forgets a deleted trip", async () => {
    const store = make();
    expect(await store.get("t1")).toEqual(emptyExtras("t1"));
    const one: TripExtras = {
      tripId: "t1",
      albums: [{ id: "a", name: "Rome", url: "https://photos.app.goo.gl/r", createdAt: 1 }],
      cover: { uri: "file:///app/covers/t1-1.jpg", fileName: "IMG.jpg", setAt: 2 },
    };
    await store.put(one);
    await store.put({ ...emptyExtras("t2"), cover: null });
    expect(await store.get("t1")).toEqual(one);
    expect((await store.all()).map((e) => e.tripId).sort()).toEqual(["t1", "t2"]);
    await store.remove("t1");
    expect(await store.get("t1")).toEqual(emptyExtras("t1"));
  });
});

test("a damaged SQLite row is read as empty, not a crash", async () => {
  const db = fakeDatabase();
  db.rows.set("t1", "{not json");
  const store = createSqliteExtrasStore(async () => db);
  expect(await store.get("t1")).toEqual(emptyExtras("t1"));
});
