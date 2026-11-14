import type { TripDocument } from "./model";
import {
  type DocumentDatabase,
  createMemoryDocumentStore,
  createSqliteDocumentStore,
} from "./store";

const doc = (id: string, tripId: string, createdAt = 1): TripDocument => ({
  id,
  tripId,
  title: id,
  category: "ticket",
  link: { kind: "trip" },
  fileName: `${id}.pdf`,
  mimeType: "application/pdf",
  sizeBytes: 10,
  uri: `file:///${id}.pdf`,
  createdAt,
});

/** Just enough SQL for the store's statements. */
function fakeDatabase(): DocumentDatabase & {
  rows: Map<string, { trip_id: string; json: string; created_at: number }>;
  sql: string[];
} {
  const rows = new Map<string, { trip_id: string; json: string; created_at: number }>();
  const sql: string[] = [];
  return {
    rows,
    sql,
    execAsync: async (s) => {
      sql.push(s);
    },
    getFirstAsync: async <T>(s: string, ...p: (string | number)[]) => {
      sql.push(s);
      return (rows.get(String(p[0])) as T | undefined) ?? null;
    },
    getAllAsync: async <T>(s: string, ...p: (string | number)[]) => {
      sql.push(s);
      return [...rows.values()]
        .filter((r) => r.trip_id === p[0])
        .sort((a, b) => b.created_at - a.created_at) as T[];
    },
    runAsync: async (s, ...p) => {
      sql.push(s);
      if (s.startsWith("INSERT"))
        rows.set(String(p[0]), {
          trip_id: String(p[1]),
          json: String(p[2]),
          created_at: Number(p[3]),
        });
      if (s.startsWith("DELETE FROM trip_document WHERE id")) rows.delete(String(p[0]));
      if (s.startsWith("DELETE FROM trip_document WHERE trip_id"))
        for (const [k, r] of rows) if (r.trip_id === p[0]) rows.delete(k);
    },
  };
}

describe.each([
  ["memory", () => createMemoryDocumentStore()],
  ["sqlite", () => createSqliteDocumentStore(async () => fakeDatabase())],
])("the %s store", (_name, make) => {
  test("lists a trip's documents, newest first, and only that trip's", async () => {
    const store = make();
    await store.put(doc("a", "t1", 1));
    await store.put(doc("b", "t1", 2));
    await store.put(doc("c", "t2", 3));
    expect((await store.list("t1")).map((d) => d.id).sort()).toEqual(["a", "b"]);
    expect(await store.get("c")).toEqual(doc("c", "t2", 3));
  });

  test("updates in place, removes one, removes a trip's and returns them", async () => {
    const store = make();
    await store.put(doc("a", "t1"));
    await store.put({ ...doc("a", "t1"), title: "Renamed" });
    expect((await store.get("a"))?.title).toBe("Renamed");
    await store.put(doc("b", "t1"));
    await store.put(doc("c", "t2"));
    await store.remove("b");
    expect(await store.get("b")).toBeNull();
    const gone = await store.removeTrip("t1");
    expect(gone.map((d) => d.id)).toEqual(["a"]);
    expect(await store.list("t1")).toEqual([]);
    expect(await store.list("t2")).toHaveLength(1);
  });
});

test("the SQLite store creates its table once, apart from the cache, and skips damaged rows", async () => {
  const db = fakeDatabase();
  const open = jest.fn(async () => db);
  const store = createSqliteDocumentStore(open);
  await store.put(doc("a", "t1"));
  db.rows.set("bad", { trip_id: "t1", json: "{oops", created_at: 0 });
  expect((await store.list("t1")).map((d) => d.id)).toEqual(["a"]);
  expect(await store.get("bad")).toBeNull();
  expect(open).toHaveBeenCalledTimes(1);
  expect(
    db.sql.filter((s) => s.startsWith("CREATE TABLE IF NOT EXISTS trip_document")),
  ).toHaveLength(1);
  expect(db.sql.some((s) => /\bcache\b/.test(s))).toBe(false);
});
