// On-device read cache (architecture 4.1, ADR 001: expo-sqlite). It stores the JSON the backend
// returned for trips and itineraries so they can be read without a connection. It is not a sync
// layer: nothing is ever written back, and nothing here edits data.

export type CacheEntry<T = unknown> = { value: T; savedAt: number };

export interface CacheStore {
  get<T>(key: string): Promise<CacheEntry<T> | null>;
  set(key: string, value: unknown, savedAt?: number): Promise<void>;
  remove(key: string): Promise<void>;
  clear(): Promise<void>;
}

/** Used by tests and as the fallback when the database cannot be opened. */
export function createMemoryStore(now: () => number = Date.now): CacheStore {
  const map = new Map<string, CacheEntry>();
  return {
    get: async <T>(key: string) => (map.get(key) as CacheEntry<T> | undefined) ?? null,
    set: async (key, value, savedAt = now()) => {
      // A JSON round trip, as the real store does, so tests cannot depend on object identity.
      map.set(key, { value: JSON.parse(JSON.stringify(value)), savedAt });
    },
    remove: async (key) => {
      map.delete(key);
    },
    clear: async () => {
      map.clear();
    },
  };
}

// The slice of expo-sqlite this file uses, so tests can supply a fake.
export interface SqliteDatabase {
  execAsync(sql: string): Promise<void>;
  getFirstAsync<T>(sql: string, ...params: (string | number)[]): Promise<T | null>;
  runAsync(sql: string, ...params: (string | number)[]): Promise<unknown>;
}

export const DATABASE_NAME = "detour-cache.db";

export function createSqliteStore(
  open: () => Promise<SqliteDatabase>,
  now: () => number = Date.now,
): CacheStore {
  let ready: Promise<SqliteDatabase> | null = null;
  const db = () => {
    ready ??= open().then(async (d) => {
      await d.execAsync(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY NOT NULL, json TEXT NOT NULL, saved_at INTEGER NOT NULL)",
      );
      return d;
    });
    return ready;
  };
  return {
    async get<T>(key: string) {
      const row = await (
        await db()
      ).getFirstAsync<{ json: string; saved_at: number }>(
        "SELECT json, saved_at FROM cache WHERE key = ?",
        key,
      );
      if (!row) return null;
      try {
        return { value: JSON.parse(row.json) as T, savedAt: row.saved_at };
      } catch {
        return null; // a damaged row is a miss, not a crash
      }
    },
    async set(key, value, savedAt = now()) {
      await (
        await db()
      ).runAsync(
        "INSERT OR REPLACE INTO cache (key, json, saved_at) VALUES (?, ?, ?)",
        key,
        JSON.stringify(value),
        savedAt,
      );
    },
    async remove(key) {
      await (await db()).runAsync("DELETE FROM cache WHERE key = ?", key);
    },
    async clear() {
      await (await db()).runAsync("DELETE FROM cache");
    },
  };
}

/** Wraps a store so that a failing database never breaks a screen: reads miss, writes are lost. */
export function safeStore(inner: CacheStore, onError?: (e: unknown) => void): CacheStore {
  const guard =
    <A extends unknown[], R>(fallback: R, fn: (...a: A) => Promise<R>) =>
    async (...a: A): Promise<R> => {
      try {
        return await fn(...a);
      } catch (e) {
        onError?.(e);
        return fallback;
      }
    };
  return {
    get: guard(null, inner.get) as CacheStore["get"],
    set: guard(undefined, inner.set),
    remove: guard(undefined, inner.remove),
    clear: guard(undefined, inner.clear),
  };
}
