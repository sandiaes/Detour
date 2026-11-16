import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { ApiClient, Trip, components } from "@detour/shared";

import { useBackend } from "../api/BackendProvider";
import { ApiError, NetworkError, call, callEmpty, describeError } from "../api/unwrap";
import type { ExchangeFiles } from "../exchange/files";
import { decodeBase64, encodeBase64 } from "../util/base64";
import {
  type LocalCover,
  type TripAlbum,
  type TripExtras,
  type TripExtrasStore,
  MAX_ALBUMS,
  MAX_ALBUM_NAME,
  createMemoryExtrasStore,
  emptyExtras,
  normaliseAlbumUrl,
} from "./extras";
import type { DocumentFiles } from "./files";
import {
  type DocCategory,
  type DocLink,
  type PickedFile,
  type TripDocument,
  newDocumentId,
  normaliseCategory,
} from "./model";
import type { DocumentStore } from "./store";

type Value = {
  store: DocumentStore;
  /** Album links and covers from the phone (ADR 031). */
  extras: TripExtrasStore;
  files: DocumentFiles;
  /** Reading and writing the trip file (ADR 028). */
  exchange: ExchangeFiles;
  version: number;
  changed: () => void;
};

const DocumentsContext = createContext<Value | null>(null);

export function DocumentsProvider({
  store,
  extras: givenExtras,
  files,
  exchange,
  children,
}: {
  store: DocumentStore;
  extras?: TripExtrasStore;
  files: DocumentFiles;
  exchange: ExchangeFiles;
  children: ReactNode;
}) {
  const [version, setVersion] = useState(0);
  const changed = useCallback(() => setVersion((v) => v + 1), []);
  const [fallbackExtras] = useState(createMemoryExtrasStore);
  const extras = givenExtras ?? fallbackExtras;
  return (
    <DocumentsContext.Provider value={{ store, extras, files, exchange, version, changed }}>
      {children}
    </DocumentsContext.Provider>
  );
}

/** The store, the device files and the change signal, for code that moves documents in bulk. */
export function useDocumentsInternals(): Value {
  return useDocumentsContext();
}

function useDocumentsContext(): Value {
  const value = useContext(DocumentsContext);
  if (!value) throw new Error("useDocuments must be used inside a DocumentsProvider");
  return value;
}

export type DocumentsState = {
  documents: TripDocument[] | undefined;
  error: string | null;
  reload: () => void;
};

/** A trip's documents, read again whenever any document changes. */
export function useTripDocuments(tripId: string): DocumentsState {
  const { store, version, changed } = useDocumentsContext();
  const [state, setState] = useState<{ key: string; docs?: TripDocument[]; error: string | null }>({
    key: "",
    error: null,
  });
  const key = `${tripId}:${version}`;
  useEffect(() => {
    let current = true;
    store.list(tripId).then(
      (docs) => current && setState({ key, docs, error: null }),
      () =>
        current &&
        setState({ key, error: "The documents on this device could not be read. Try again." }),
    );
    return () => {
      current = false;
    };
  }, [store, tripId, key]);
  return { documents: state.docs, error: state.error, reload: changed };
}

export function useDocument(id: string | undefined): TripDocument | null | undefined {
  const { store, version } = useDocumentsContext();
  const [doc, setDoc] = useState<{ key: string; doc: TripDocument | null } | null>(null);
  const key = `${id}:${version}`;
  useEffect(() => {
    if (!id) return;
    let current = true;
    store.get(id).then(
      (found) => current && setDoc({ key, doc: found }),
      () => current && setDoc({ key, doc: null }),
    );
    return () => {
      current = false;
    };
  }, [store, id, key]);
  if (!id) return null;
  return doc?.key === key ? doc.doc : doc ? doc.doc : undefined;
}

export type DocumentFields = {
  title: string;
  category: DocCategory;
  link: DocLink;
  date?: string | null;
  notes?: string | null;
};

// -- documents shared with the trip (ADR 034, step 6) -------------------------------------------

/** A document was kept on this phone, but could not be uploaded (offline, too large, refused). */
export class UploadError extends Error {}

type ServerDocument = components["schemas"]["TripDocumentInfo"];
type ServerContentType = components["schemas"]["TripDocumentUpload"]["content_type"];

const UPLOADABLE: readonly string[] = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
  "image/heic",
  "image/heif",
];

// Documents of a trip that starts within this many days (or is under way) are downloaded ahead,
// so tickets open without a signal.
export const DOWNLOAD_AHEAD_DAYS = 14;

type DocDeps = {
  store: DocumentStore;
  files: DocumentFiles;
  client: ApiClient;
  changed: () => void;
};

function serverFields(doc: Pick<TripDocument, "title" | "category" | "link" | "date" | "notes">) {
  return {
    title: doc.title,
    category: doc.category,
    link: doc.link,
    date: doc.date ?? null,
    notes: doc.notes ?? null,
  };
}

/** Whether a trip's shared documents should already be on the phone. */
export function downloadsAhead(trip: Trip, today = new Date()): boolean {
  if (!trip.start_date) return false;
  const day = 86_400_000;
  const start = Date.parse(`${trip.start_date}T00:00:00Z`);
  const end = Date.parse(`${trip.end_date ?? trip.start_date}T00:00:00Z`);
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return start - now <= DOWNLOAD_AHEAD_DAYS * day && end >= now;
}

async function uploadDocument(deps: DocDeps, doc: TripDocument): Promise<TripDocument> {
  if (!UPLOADABLE.includes(doc.mimeType)) {
    throw new UploadError("This kind of file cannot be uploaded; it stays on this phone.");
  }
  const serverId = doc.serverId ?? (UUID.test(doc.id) ? doc.id : newDocumentId());
  try {
    const bytes = await deps.files.readBytes(doc.uri);
    await call(
      deps.client.POST("/v1/trips/{trip_id}/documents", {
        params: { path: { trip_id: doc.tripId } },
        body: {
          id: serverId,
          ...serverFields(doc),
          file_name: doc.fileName.slice(0, 200) || "document",
          content_type: doc.mimeType as ServerContentType,
          data: encodeBase64(bytes),
        },
      }),
    );
  } catch (e) {
    throw new UploadError(describeError(e));
  }
  const shared = { ...doc, serverId };
  await deps.store.put(shared);
  deps.changed();
  return shared;
}

async function downloadDocument(deps: DocDeps, doc: TripDocument): Promise<TripDocument> {
  if (!doc.serverId) return doc;
  const file = await call(
    deps.client.GET("/v1/trips/{trip_id}/documents/{document_id}/file", {
      params: { path: { trip_id: doc.tripId, document_id: doc.serverId } },
    }),
  );
  const uri = await deps.files.keepDocumentBytes(
    decodeBase64(file.data),
    doc.tripId,
    doc.id,
    doc.fileName,
  );
  const kept = { ...doc, uri };
  await deps.store.put(kept);
  deps.changed();
  return kept;
}

/** Bring the phone's documents of a trip in line with the server: new shared documents are
 * listed (and downloaded ahead for a trip that is near), changed ones take the new description,
 * and those deleted elsewhere go. Documents only on this phone are left alone. */
async function syncDocuments(deps: DocDeps, trip: Trip): Promise<void> {
  const server: ServerDocument[] = await call(
    deps.client.GET("/v1/trips/{trip_id}/documents", { params: { path: { trip_id: trip.id } } }),
  );
  const local = await deps.store.list(trip.id);
  const byServer = new Map(local.filter((d) => d.serverId).map((d) => [d.serverId as string, d]));
  let changed = false;
  for (const s of server) {
    const fields = {
      title: s.title,
      category: normaliseCategory(s.category),
      link: s.link as DocLink,
      date: s.date ?? null,
      notes: s.notes ?? null,
    };
    const here = byServer.get(s.id);
    if (!here) {
      await deps.store.put({
        id: s.id,
        tripId: trip.id,
        ...fields,
        fileName: s.file_name,
        mimeType: s.content_type,
        sizeBytes: s.bytes,
        uri: "",
        createdAt: Date.parse(s.created_at) || Date.now(),
        serverId: s.id,
      });
      changed = true;
    } else if (JSON.stringify(serverFields(here)) !== JSON.stringify(serverFields(fields))) {
      await deps.store.put({ ...here, ...fields });
      changed = true;
    }
  }
  const onServer = new Set(server.map((s) => s.id));
  for (const d of local) {
    if (d.serverId && !onServer.has(d.serverId)) {
      await deps.store.remove(d.id);
      if (d.uri) await deps.files.remove(d.uri).catch(() => undefined);
      changed = true;
    }
  }
  if (changed) deps.changed();
  if (downloadsAhead(trip)) {
    for (const d of await deps.store.list(trip.id)) {
      if (d.serverId && !d.uri) await downloadDocument(deps, d).catch(() => undefined);
    }
  }
}

export function useDocumentActions() {
  const { store, extras, files, changed } = useDocumentsContext();
  const { state } = useBackend();
  const client = state.phase === "ready" ? state.connection.client : null;
  const deps = useCallback((): DocDeps => {
    if (!client) throw new NetworkError("Not connected to the server.");
    return { store, files, client, changed };
  }, [client, store, files, changed]);

  /** Keeps the picked file on this phone; with `share`, also uploads it for everyone on the trip.
   * A failed upload keeps the phone's copy and throws `UploadError` with the document attached. */
  const add = useCallback(
    async (
      tripId: string,
      picked: PickedFile,
      fields: DocumentFields,
      share = false,
    ): Promise<TripDocument> => {
      const id = newDocumentId();
      const uri = await files.keep(picked, tripId, id);
      const doc: TripDocument = {
        id,
        tripId,
        ...fields,
        title: fields.title.trim(),
        notes: fields.notes?.trim() || null,
        date: fields.date || null,
        fileName: picked.name,
        mimeType: picked.mimeType,
        sizeBytes: picked.size,
        uri,
        createdAt: Date.now(),
      };
      try {
        await store.put(doc);
      } catch (e) {
        await files.remove(uri).catch(() => undefined); // never leave a file nobody lists
        throw e;
      }
      changed();
      if (!share) return doc;
      try {
        return await uploadDocument(deps(), doc);
      } catch (e) {
        throw e instanceof UploadError ? Object.assign(e, { doc }) : e;
      }
    },
    [files, store, changed, deps],
  );

  /** A shared document is changed on the server first, so both phones agree. */
  const update = useCallback(
    async (doc: TripDocument, fields: DocumentFields) => {
      const next = {
        ...doc,
        ...fields,
        title: fields.title.trim(),
        notes: fields.notes?.trim() || null,
        date: fields.date || null,
      };
      if (doc.serverId) {
        await call(
          deps().client.PATCH("/v1/trips/{trip_id}/documents/{document_id}", {
            params: { path: { trip_id: doc.tripId, document_id: doc.serverId } },
            body: serverFields(next),
          }),
        );
      }
      await store.put(next);
      changed();
    },
    [store, changed, deps],
  );

  /** A shared document is deleted for everyone on the trip, then here. */
  const remove = useCallback(
    async (doc: TripDocument) => {
      if (doc.serverId) {
        await callEmpty(
          deps().client.DELETE("/v1/trips/{trip_id}/documents/{document_id}", {
            params: { path: { trip_id: doc.tripId, document_id: doc.serverId } },
          }),
        ).catch((e: unknown) => {
          if (!(e instanceof ApiError && e.status === 404)) throw e; // already gone is fine
        });
      }
      await store.remove(doc.id);
      if (doc.uri) await files.remove(doc.uri).catch(() => undefined);
      changed();
    },
    [files, store, changed, deps],
  );

  /** Upload a document kept only on this phone, for everyone on the trip. */
  const share = useCallback((doc: TripDocument) => uploadDocument(deps(), doc), [deps]);

  /** Keep a shared document on this phone only: the server's copy is deleted for everyone. */
  const unshare = useCallback(
    async (doc: TripDocument) => {
      if (!doc.serverId) return;
      await callEmpty(
        deps().client.DELETE("/v1/trips/{trip_id}/documents/{document_id}", {
          params: { path: { trip_id: doc.tripId, document_id: doc.serverId } },
        }),
      ).catch((e: unknown) => {
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      });
      await store.put({ ...doc, serverId: null });
      changed();
    },
    [store, changed, deps],
  );

  /** Opens the file with the phone's viewer, downloading a shared one first if needed. */
  const open = useCallback(
    async (doc: TripDocument) => {
      const ready = doc.uri ? doc : await downloadDocument(deps(), doc);
      await files.open(ready);
    },
    [files, deps],
  );

  /** Called when a trip is deleted: its documents, album links and phone cover go too. */
  const removeTrip = useCallback(
    async (tripId: string) => {
      const gone = await store.removeTrip(tripId);
      await Promise.all(
        gone.filter((d) => d.uri).map((d) => files.remove(d.uri).catch(() => undefined)),
      );
      const own = await extras.get(tripId).catch(() => emptyExtras(tripId));
      await extras.remove(tripId).catch(() => undefined);
      if (own.cover) await files.remove(own.cover.uri).catch(() => undefined);
      if (gone.length || own.cover || own.albums.length) changed();
    },
    [files, store, extras, changed],
  );

  return { pick: files.pick, open, add, update, remove, share, unshare, removeTrip };
}

// Album links and covers from the phone (ADR 031).

export type ExtrasState = { extras: TripExtras | undefined; error: string | null };

/** A trip's album links and phone cover, read again whenever anything on the phone changes. */
export function useTripExtras(tripId: string): ExtrasState {
  const { extras, version } = useDocumentsContext();
  const [state, setState] = useState<{ key: string; value?: TripExtras; error: string | null }>({
    key: "",
    error: null,
  });
  const key = `${tripId}:${version}`;
  useEffect(() => {
    let current = true;
    extras.get(tripId).then(
      (value) => current && setState({ key, value, error: null }),
      () =>
        current &&
        setState({ key, error: "The albums saved on this phone could not be read. Try again." }),
    );
    return () => {
      current = false;
    };
  }, [extras, tripId, key]);
  return { extras: state.value, error: state.error };
}

/** Every trip's extras on this phone, by trip (the trips list, the Photos screen). */
export function useAllTripExtras(): Record<string, TripExtras> {
  const { extras, version } = useDocumentsContext();
  const [all, setAll] = useState<TripExtras[]>([]);
  useEffect(() => {
    let current = true;
    extras.all().then(
      (rows) => current && setAll(rows),
      () => undefined, // nothing readable: covers fall back to the destination's
    );
    return () => {
      current = false;
    };
  }, [extras, version]);
  return useMemo(() => Object.fromEntries(all.map((e) => [e.tripId, e])), [all]);
}

/** The cover chosen from the phone for a trip, if any. */
export function useLocalCover(tripId: string): LocalCover | null {
  return useTripExtras(tripId).extras?.cover ?? null;
}

export class AlbumError extends Error {}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type ServerAlbum = components["schemas"]["TripAlbum"];

function toLocal(a: ServerAlbum): TripAlbum {
  return { id: a.id, name: a.name, url: a.url, createdAt: Date.parse(a.created_at) || 0 };
}

const ALBUM_MESSAGES: Record<string, string> = {
  album_exists: "This album is already linked to the trip.",
  limit_reached: `A trip can have up to ${MAX_ALBUMS} albums.`,
  album_url: "Paste the album's share link (it starts with https://).",
};

/**
 * Album links and the cover chosen from a phone (ADR 031). Since ADR 034 step 5 the server holds
 * them for everyone on the trip; the phone keeps a copy (the `trip_extra` table and the `covers/`
 * folder) so they still show offline. Each change goes to the server first; `syncTrip` brings the
 * phone's copy in line with the server and uploads what an older build kept only on the phone.
 */
export function useExtrasActions() {
  const { store, extras, files, changed } = useDocumentsContext();
  const { state } = useBackend();
  const client = state.phase === "ready" ? state.connection.client : null;
  const need = useCallback(() => {
    if (!client) throw new NetworkError("Not connected to the server.");
    return client;
  }, [client]);

  /** Write the server's albums into the phone's copy. */
  const keepAlbums = useCallback(
    async (tripId: string, albums: ServerAlbum[]) => {
      const now = await extras.get(tripId);
      await extras.put({ ...now, albums: albums.map(toLocal) });
      changed();
    },
    [extras, changed],
  );

  const albumCall = useCallback(async <T,>(request: Promise<T>): Promise<T> => {
    try {
      return await request;
    } catch (e) {
      if (e instanceof ApiError && e.code && ALBUM_MESSAGES[e.code]) {
        throw new AlbumError(ALBUM_MESSAGES[e.code]);
      }
      throw e;
    }
  }, []);

  const listAlbums = useCallback(
    (tripId: string) =>
      call(need().GET("/v1/trips/{trip_id}/albums", { params: { path: { trip_id: tripId } } })),
    [need],
  );

  const addAlbum = useCallback(
    async (tripId: string, name: string, link: string): Promise<TripAlbum> => {
      const url = normaliseAlbumUrl(link);
      if (!url) throw new AlbumError("Paste the album's share link (it starts with https://).");
      const added = await albumCall(
        call(
          need().POST("/v1/trips/{trip_id}/albums", {
            params: { path: { trip_id: tripId } },
            body: { url, name: name.trim().slice(0, MAX_ALBUM_NAME) || null },
          }),
        ),
      );
      await keepAlbums(tripId, await listAlbums(tripId));
      return toLocal(added);
    },
    [need, albumCall, keepAlbums, listAlbums],
  );

  const renameAlbum = useCallback(
    async (tripId: string, albumId: string, name: string) => {
      const clean = name.trim().slice(0, MAX_ALBUM_NAME);
      if (!clean) return;
      await albumCall(
        call(
          need().PATCH("/v1/trips/{trip_id}/albums/{album_id}", {
            params: { path: { trip_id: tripId, album_id: albumId } },
            body: { name: clean },
          }),
        ),
      );
      await keepAlbums(tripId, await listAlbums(tripId));
    },
    [need, albumCall, keepAlbums, listAlbums],
  );

  const removeAlbum = useCallback(
    async (tripId: string, albumId: string) => {
      await callEmpty(
        need().DELETE("/v1/trips/{trip_id}/albums/{album_id}", {
          params: { path: { trip_id: tripId, album_id: albumId } },
        }),
      ).catch((e: unknown) => {
        if (!(e instanceof ApiError && e.status === 404)) throw e; // already gone is fine
      });
      await keepAlbums(tripId, await listAlbums(tripId));
    },
    [need, keepAlbums, listAlbums],
  );

  /** Upload the phone's cover of a trip and note the server's id on the phone's copy. */
  const uploadCover = useCallback(
    async (tripId: string, cover: LocalCover): Promise<void> => {
      const bytes = await files.readBytes(cover.uri);
      const lower = cover.fileName.toLowerCase();
      const contentType = lower.endsWith(".png")
        ? "image/png"
        : lower.endsWith(".webp")
          ? "image/webp"
          : "image/jpeg";
      const stored = await call(
        need().PUT("/v1/trips/{trip_id}/own-cover", {
          params: { path: { trip_id: tripId } },
          body: { content_type: contentType, data: encodeBase64(bytes) },
        }),
      );
      const now = await extras.get(tripId);
      if (now.cover?.uri === cover.uri) {
        await extras.put({ ...now, cover: { ...now.cover, serverId: stored.id } });
        changed();
      }
    },
    [files, need, extras, changed],
  );

  /** Copies a picked picture in as the trip's cover (shown at once) and uploads it for everyone
   * on the trip; the previous copy is deleted. A failed upload leaves the phone's copy and
   * throws, so the screen can say it is on this phone only. */
  const setLocalCover = useCallback(
    async (tripId: string, picked: PickedFile): Promise<LocalCover> => {
      const uri = await files.keepCover(picked, tripId);
      const cover: LocalCover = { uri, fileName: picked.name, setAt: Date.now() };
      let previous: LocalCover | null = null;
      try {
        const now = await extras.get(tripId);
        previous = now.cover;
        await extras.put({ ...now, cover });
      } catch (e) {
        await files.remove(uri).catch(() => undefined); // never leave a file nobody lists
        throw e;
      }
      if (previous && previous.uri !== uri) await files.remove(previous.uri).catch(() => undefined);
      changed();
      await uploadCover(tripId, cover);
      return cover;
    },
    [extras, files, changed, uploadCover],
  );

  /** A picture chosen before its trip exists (the new-trip screen): copied in now, while the
   * picker's permission lasts, and adopted by `adoptCover` once the trip is created. */
  const stageCover = useCallback(
    (picked: PickedFile): Promise<string> => files.keepCover(picked, "new"),
    [files],
  );

  const adoptCover = useCallback(
    async (tripId: string, uri: string, fileName: string) => {
      const now = await extras.get(tripId);
      const cover: LocalCover = { uri, fileName, setAt: Date.now() };
      await extras.put({ ...now, cover });
      if (now.cover && now.cover.uri !== uri)
        await files.remove(now.cover.uri).catch(() => undefined);
      changed();
      // Shared from the start; offline, the next sync uploads it.
      await uploadCover(tripId, cover).catch(() => undefined);
    },
    [extras, files, changed, uploadCover],
  );

  /** Removes a staged picture that was never adopted. */
  const dropStaged = useCallback(
    (uri: string) => files.remove(uri).catch(() => undefined),
    [files],
  );

  /** Back to the destination's photo (or the illustration), for everyone on the trip. */
  const clearLocalCover = useCallback(
    async (tripId: string) => {
      await callEmpty(
        need().DELETE("/v1/trips/{trip_id}/own-cover", { params: { path: { trip_id: tripId } } }),
      ).catch((e: unknown) => {
        if (!(e instanceof ApiError && e.status === 404)) throw e; // none on the server
      });
      const now = await extras.get(tripId);
      if (!now.cover) return;
      await extras.put({ ...now, cover: null });
      await files.remove(now.cover.uri).catch(() => undefined);
      changed();
    },
    [need, extras, changed, files],
  );

  /**
   * Bring the phone's copy of a trip's albums and cover in line with the server: albums an older
   * build kept only here are uploaded once, then the server's list is kept; the server's cover is
   * downloaded when it is not the one here, a cover removed elsewhere is removed here, and a cover
   * only on this phone is uploaded. Failures are quiet: the phone's copy stays as it was.
   */
  const syncTrip = useCallback(
    async (trip: Trip): Promise<void> => {
      if (!client) return;
      const local = await extras.get(trip.id);
      let server = await listAlbums(trip.id);
      const onlyHere = local.albums.filter(
        (a) => !UUID.test(a.id) && !server.some((s) => s.url === a.url),
      );
      for (const album of onlyHere) {
        await call(
          client.POST("/v1/trips/{trip_id}/albums", {
            params: { path: { trip_id: trip.id } },
            body: { url: album.url, name: album.name },
          }),
        ).catch(() => undefined);
      }
      if (onlyHere.length > 0) server = await listAlbums(trip.id);
      const sameAlbums =
        JSON.stringify(local.albums.map((a) => [a.id, a.name, a.url])) ===
        JSON.stringify(server.map((a) => [a.id, a.name, a.url]));
      if (!sameAlbums) await keepAlbums(trip.id, server);

      await syncDocuments({ store, files, client, changed }, trip).catch(() => undefined);

      const own = trip.own_cover ?? null;
      const cover = (await extras.get(trip.id)).cover;
      if (own && cover?.serverId !== own.id) {
        const file = await call(
          client.GET("/v1/trips/{trip_id}/own-cover", { params: { path: { trip_id: trip.id } } }),
        );
        const uri = await files.keepCoverBytes(decodeBase64(file.data), trip.id);
        const now = await extras.get(trip.id);
        await extras.put({
          ...now,
          cover: { uri, fileName: "cover.jpg", setAt: Date.now(), serverId: file.id },
        });
        if (now.cover) await files.remove(now.cover.uri).catch(() => undefined);
        changed();
      } else if (!own && cover?.serverId) {
        const now = await extras.get(trip.id);
        await extras.put({ ...now, cover: null });
        await files.remove(cover.uri).catch(() => undefined);
        changed();
      } else if (!own && cover) {
        await uploadCover(trip.id, cover);
      }
    },
    [client, store, extras, files, changed, listAlbums, keepAlbums, uploadCover],
  );

  return {
    pickImage: files.pickImage,
    addAlbum,
    renameAlbum,
    removeAlbum,
    setLocalCover,
    clearLocalCover,
    stageCover,
    adoptCover,
    dropStaged,
    syncTrip,
  };
}

// How long a trip synced once is left alone, unless its cover changed on the server.
const SYNC_AGAIN_MS = 5 * 60_000;

/** Keep the phone's albums and covers of these trips in line with the server (ADR 034, step 5):
 * once per trip, again after a few minutes or when the trip's cover changed elsewhere. */
export function useSyncTrips(trips: Trip[] | undefined): void {
  const { syncTrip } = useExtrasActions();
  const done = useRef(new Map<string, { cover: string | null; at: number }>());
  useEffect(() => {
    if (!trips) return;
    const now = Date.now();
    for (const trip of trips) {
      const cover = trip.own_cover?.id ?? null;
      const last = done.current.get(trip.id);
      if (last && last.cover === cover && now - last.at < SYNC_AGAIN_MS) continue;
      done.current.set(trip.id, { cover, at: now });
      void syncTrip(trip).catch(() => {
        done.current.delete(trip.id); // try again next time
      });
    }
  }, [trips, syncTrip]);
}
