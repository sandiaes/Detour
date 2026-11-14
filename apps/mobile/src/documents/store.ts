import { type TripDocument, normaliseCategory } from "./model";

// Where documents are listed (ADR 023): a table in the app's SQLite database, next to the read
// cache but separate from it (clearing the cache never removes a document). The files themselves
// are in the app's private storage (files.ts).

export interface DocumentStore {
  list(tripId: string): Promise<TripDocument[]>;
  get(id: string): Promise<TripDocument | null>;
  put(doc: TripDocument): Promise<void>;
  remove(id: string): Promise<void>;
  removeTrip(tripId: string): Promise<TripDocument[]>;
}

export function createMemoryDocumentStore(initial: TripDocument[] = []): DocumentStore {
  const map = new Map(initial.map((d) => [d.id, d]));
  const copy = (d: TripDocument) => JSON.parse(JSON.stringify(d)) as TripDocument;
  return {
    list: async (tripId) => [...map.values()].filter((d) => d.tripId === tripId).map(copy),
    get: async (id) => (map.has(id) ? copy(map.get(id) as TripDocument) : null),
    put: async (doc) => {
      map.set(doc.id, copy(doc));
    },
    remove: async (id) => {
      map.delete(id);
    },
    removeTrip: async (tripId) => {
      const gone = [...map.values()].filter((d) => d.tripId === tripId);
      for (const d of gone) map.delete(d.id);
      return gone.map(copy);
    },
  };
}

/** The slice of expo-sqlite this store uses. */
export interface DocumentDatabase {
  execAsync(sql: string): Promise<void>;
  getFirstAsync<T>(sql: string, ...params: (string | number)[]): Promise<T | null>;
  getAllAsync<T>(sql: string, ...params: (string | number)[]): Promise<T[]>;
  runAsync(sql: string, ...params: (string | number)[]): Promise<unknown>;
}

export function createSqliteDocumentStore(open: () => Promise<DocumentDatabase>): DocumentStore {
  let ready: Promise<DocumentDatabase> | null = null;
  const db = () => {
    ready ??= open().then(async (d) => {
      await d.execAsync(
        "CREATE TABLE IF NOT EXISTS trip_document (id TEXT PRIMARY KEY NOT NULL, trip_id TEXT NOT NULL, json TEXT NOT NULL, created_at INTEGER NOT NULL); " +
          "CREATE INDEX IF NOT EXISTS trip_document_trip ON trip_document (trip_id)",
      );
      return d;
    });
    return ready;
  };
  const parse = (json: string): TripDocument | null => {
    try {
      const doc = JSON.parse(json) as TripDocument;
      return { ...doc, category: normaliseCategory(doc.category) };
    } catch {
      return null; // a damaged row is skipped, not a crash
    }
  };
  const list = async (tripId: string) =>
    (
      await (
        await db()
      ).getAllAsync<{ json: string }>(
        "SELECT json FROM trip_document WHERE trip_id = ? ORDER BY created_at DESC",
        tripId,
      )
    )
      .map((r) => parse(r.json))
      .filter((d): d is TripDocument => d !== null);
  return {
    list,
    async get(id) {
      const row = await (
        await db()
      ).getFirstAsync<{ json: string }>("SELECT json FROM trip_document WHERE id = ?", id);
      return row ? parse(row.json) : null;
    },
    async put(doc) {
      await (
        await db()
      ).runAsync(
        "INSERT OR REPLACE INTO trip_document (id, trip_id, json, created_at) VALUES (?, ?, ?, ?)",
        doc.id,
        doc.tripId,
        JSON.stringify(doc),
        doc.createdAt,
      );
    },
    async remove(id) {
      await (await db()).runAsync("DELETE FROM trip_document WHERE id = ?", id);
    },
    async removeTrip(tripId) {
      const gone = await list(tripId);
      await (await db()).runAsync("DELETE FROM trip_document WHERE trip_id = ?", tripId);
      return gone;
    },
  };
}
