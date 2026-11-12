import { type SqliteDatabase, createMemoryStore, createSqliteStore, safeStore } from "./store";

function fakeDatabase(): SqliteDatabase & {
  rows: Map<string, { json: string; saved_at: number }>;
  sql: string[];
} {
  const rows = new Map<string, { json: string; saved_at: number }>();
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
    runAsync: async (s, ...p) => {
      sql.push(s);
      if (s.startsWith("INSERT"))
        rows.set(String(p[0]), { json: String(p[1]), saved_at: Number(p[2]) });
      if (s.startsWith("DELETE FROM cache WHERE")) rows.delete(String(p[0]));
      if (s === "DELETE FROM cache") rows.clear();
    },
  };
}

test("the memory store round-trips JSON and keeps the save time", async () => {
  const store = createMemoryStore(() => 5);
  await store.set("a", { n: 1 });
  expect(await store.get("a")).toEqual({ value: { n: 1 }, savedAt: 5 });
  await store.remove("a");
  expect(await store.get("a")).toBeNull();
});

test("the sqlite store creates its table once and reads what it wrote", async () => {
  const db = fakeDatabase();
  const open = jest.fn(async () => db);
  const store = createSqliteStore(open, () => 99);
  await store.set("trips", [{ id: 1 }]);
  await store.set("trips", [{ id: 2 }]);
  expect(await store.get("trips")).toEqual({ value: [{ id: 2 }], savedAt: 99 });
  expect(open).toHaveBeenCalledTimes(1);
  expect(db.sql.filter((s) => s.startsWith("CREATE TABLE"))).toHaveLength(1);
  await store.clear();
  expect(await store.get("trips")).toBeNull();
});

test("a damaged row is a miss, not an error", async () => {
  const db = fakeDatabase();
  db.rows.set("bad", { json: "{not json", saved_at: 1 });
  const store = createSqliteStore(async () => db);
  expect(await store.get("bad")).toBeNull();
});

test("a failing database never breaks a screen", async () => {
  const onError = jest.fn();
  const store = safeStore(
    createSqliteStore(async () => {
      throw new Error("cannot open");
    }),
    onError,
  );
  expect(await store.get("x")).toBeNull();
  await expect(store.set("x", 1)).resolves.toBeUndefined();
  expect(onError).toHaveBeenCalledTimes(2);
});
