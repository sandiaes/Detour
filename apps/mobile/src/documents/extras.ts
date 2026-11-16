import type { DocumentDatabase } from "./store";

// What a trip keeps on this phone besides documents (ADR 031): links to the user's own photo
// albums (opened in their app, never read by Detour) and a cover photo chosen from the phone.
// Nothing here is sent to the backend; the album links leave the phone only in a trip file the
// user exports.

/** A link to a photo album the user keeps elsewhere (a Google Photos shared album, usually). */
export type TripAlbum = { id: string; name: string; url: string; createdAt: number };

/** A cover photo copied from the phone into the app's private storage. */
export type LocalCover = { uri: string; fileName: string; setAt: number };

export type TripExtras = { tripId: string; albums: TripAlbum[]; cover: LocalCover | null };

export const MAX_ALBUMS = 20;
export const MAX_ALBUM_NAME = 80;
export const MAX_ALBUM_URL = 2000;

export function emptyExtras(tripId: string): TripExtras {
  return { tripId, albums: [], cover: null };
}

const GOOGLE_PHOTOS_HOSTS = ["photos.app.goo.gl", "photos.google.com", "goo.gl"];

/**
 * The album link as typed or pasted, cleaned: surrounding words and spaces are dropped (a share
 * message often reads "Check out this album: https://…"), a bare "photos.app.goo.gl/…" gets
 * https://, and only an https web address is accepted. Null when there is no such address.
 */
export function normaliseAlbumUrl(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const found = /https?:\/\/\S+/i.exec(trimmed)?.[0];
  let candidate = found ?? (/^[a-z0-9.-]+\.[a-z]{2,}\/\S*$/i.test(trimmed) ? trimmed : null);
  if (!candidate) return null;
  candidate = candidate.replace(/[)\].,;!?'"]+$/, "");
  if (!/^https?:\/\//i.test(candidate)) candidate = `https://${candidate}`;
  if (/^http:\/\//i.test(candidate)) return null; // an album link is always https
  if (candidate.length > MAX_ALBUM_URL) return null;
  const host = hostOf(candidate);
  if (!host || !host.includes(".")) return null;
  return candidate;
}

export function hostOf(url: string): string | null {
  const match = /^https:\/\/([^/?#:@\s]+)(?::\d+)?(?:[/?#]|$)/i.exec(url);
  return match ? (match[1] as string).toLowerCase() : null;
}

export function isGooglePhotos(url: string): boolean {
  const host = hostOf(url);
  if (!host) return false;
  if (host === "goo.gl") return /^https:\/\/goo\.gl\/photos\//i.test(url);
  return GOOGLE_PHOTOS_HOSTS.includes(host);
}

/** Where the album lives, in words: "Google Photos", else the site's address. */
export function albumSource(url: string): string {
  if (isGooglePhotos(url)) return "Google Photos";
  return (hostOf(url) ?? "a web page").replace(/^www\./, "");
}

export function newAlbumId(random: () => number = Math.random, now = Date.now): string {
  return `album-${now().toString(36)}-${Math.floor(random() * 0x100000000).toString(36)}`;
}

/** Keeps a damaged or hand-made row from crashing a screen. */
export function sanitiseExtras(tripId: string, raw: unknown): TripExtras {
  const out = emptyExtras(tripId);
  if (typeof raw !== "object" || raw === null) return out;
  const v = raw as Partial<TripExtras>;
  if (Array.isArray(v.albums)) {
    for (const a of v.albums.slice(0, MAX_ALBUMS) as Partial<TripAlbum>[]) {
      const url = typeof a?.url === "string" ? normaliseAlbumUrl(a.url) : null;
      if (!url) continue;
      out.albums.push({
        id: typeof a.id === "string" ? a.id : newAlbumId(),
        name: typeof a.name === "string" && a.name.trim() ? a.name.trim() : "Trip album",
        url,
        createdAt: typeof a.createdAt === "number" ? a.createdAt : 0,
      });
    }
  }
  const c = v.cover as Partial<LocalCover> | null | undefined;
  if (c && typeof c.uri === "string" && c.uri) {
    out.cover = {
      uri: c.uri,
      fileName: typeof c.fileName === "string" ? c.fileName : "photo",
      setAt: typeof c.setAt === "number" ? c.setAt : 0,
    };
  }
  return out;
}

export interface TripExtrasStore {
  get(tripId: string): Promise<TripExtras>;
  all(): Promise<TripExtras[]>;
  put(extras: TripExtras): Promise<void>;
  remove(tripId: string): Promise<void>;
}

export function createMemoryExtrasStore(initial: TripExtras[] = []): TripExtrasStore {
  const map = new Map(initial.map((e) => [e.tripId, e]));
  const copy = (e: TripExtras) => JSON.parse(JSON.stringify(e)) as TripExtras;
  return {
    get: async (tripId) => copy(map.get(tripId) ?? emptyExtras(tripId)),
    all: async () => [...map.values()].map(copy),
    put: async (extras) => {
      map.set(extras.tripId, copy(extras));
    },
    remove: async (tripId) => {
      map.delete(tripId);
    },
  };
}

/** A table in the app's SQLite database, beside `trip_document` (ADR 023). */
export function createSqliteExtrasStore(open: () => Promise<DocumentDatabase>): TripExtrasStore {
  let ready: Promise<DocumentDatabase> | null = null;
  const db = () => {
    ready ??= open().then(async (d) => {
      await d.execAsync(
        "CREATE TABLE IF NOT EXISTS trip_extra (trip_id TEXT PRIMARY KEY NOT NULL, json TEXT NOT NULL)",
      );
      return d;
    });
    return ready;
  };
  const parse = (tripId: string, json: string) => {
    try {
      return sanitiseExtras(tripId, JSON.parse(json));
    } catch {
      return emptyExtras(tripId); // a damaged row is read as empty, not a crash
    }
  };
  return {
    async get(tripId) {
      const row = await (
        await db()
      ).getFirstAsync<{ json: string }>("SELECT json FROM trip_extra WHERE trip_id = ?", tripId);
      return row ? parse(tripId, row.json) : emptyExtras(tripId);
    },
    async all() {
      const rows = await (
        await db()
      ).getAllAsync<{ trip_id: string; json: string }>("SELECT trip_id, json FROM trip_extra");
      return rows.map((r) => parse(r.trip_id, r.json));
    },
    async put(extras) {
      await (
        await db()
      ).runAsync(
        "INSERT OR REPLACE INTO trip_extra (trip_id, json) VALUES (?, ?)",
        extras.tripId,
        JSON.stringify(extras),
      );
    },
    async remove(tripId) {
      await (await db()).runAsync("DELETE FROM trip_extra WHERE trip_id = ?", tripId);
    },
  };
}
