import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { ExchangeFiles } from "../exchange/files";
import {
  type LocalCover,
  type TripAlbum,
  type TripExtras,
  type TripExtrasStore,
  MAX_ALBUMS,
  MAX_ALBUM_NAME,
  createMemoryExtrasStore,
  emptyExtras,
  newAlbumId,
  normaliseAlbumUrl,
} from "./extras";
import type { DocumentFiles } from "./files";
import {
  type DocCategory,
  type DocLink,
  type PickedFile,
  type TripDocument,
  newDocumentId,
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

export function useDocumentActions() {
  const { store, extras, files, changed } = useDocumentsContext();

  const add = useCallback(
    async (tripId: string, picked: PickedFile, fields: DocumentFields): Promise<TripDocument> => {
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
      return doc;
    },
    [files, store, changed],
  );

  const update = useCallback(
    async (doc: TripDocument, fields: DocumentFields) => {
      await store.put({
        ...doc,
        ...fields,
        title: fields.title.trim(),
        notes: fields.notes?.trim() || null,
        date: fields.date || null,
      });
      changed();
    },
    [store, changed],
  );

  const remove = useCallback(
    async (doc: TripDocument) => {
      await store.remove(doc.id);
      await files.remove(doc.uri).catch(() => undefined);
      changed();
    },
    [files, store, changed],
  );

  /** Called when a trip is deleted: its documents, album links and phone cover go too. */
  const removeTrip = useCallback(
    async (tripId: string) => {
      const gone = await store.removeTrip(tripId);
      await Promise.all(gone.map((d) => files.remove(d.uri).catch(() => undefined)));
      const own = await extras.get(tripId).catch(() => emptyExtras(tripId));
      await extras.remove(tripId).catch(() => undefined);
      if (own.cover) await files.remove(own.cover.uri).catch(() => undefined);
      if (gone.length || own.cover || own.albums.length) changed();
    },
    [files, store, extras, changed],
  );

  return { pick: files.pick, open: files.open, add, update, remove, removeTrip };
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

export function useExtrasActions() {
  const { extras, files, changed } = useDocumentsContext();

  const addAlbum = useCallback(
    async (tripId: string, name: string, link: string): Promise<TripAlbum> => {
      const url = normaliseAlbumUrl(link);
      if (!url) throw new AlbumError("Paste the album's share link (it starts with https://).");
      const now = await extras.get(tripId);
      if (now.albums.length >= MAX_ALBUMS) {
        throw new AlbumError(`A trip can have up to ${MAX_ALBUMS} albums.`);
      }
      if (now.albums.some((a) => a.url === url)) {
        throw new AlbumError("This album is already linked to the trip.");
      }
      const album: TripAlbum = {
        id: newAlbumId(),
        name: name.trim().slice(0, MAX_ALBUM_NAME) || "Trip album",
        url,
        createdAt: Date.now(),
      };
      await extras.put({ ...now, albums: [...now.albums, album] });
      changed();
      return album;
    },
    [extras, changed],
  );

  const renameAlbum = useCallback(
    async (tripId: string, albumId: string, name: string) => {
      const now = await extras.get(tripId);
      await extras.put({
        ...now,
        albums: now.albums.map((a) =>
          a.id === albumId ? { ...a, name: name.trim().slice(0, MAX_ALBUM_NAME) || a.name } : a,
        ),
      });
      changed();
    },
    [extras, changed],
  );

  const removeAlbum = useCallback(
    async (tripId: string, albumId: string) => {
      const now = await extras.get(tripId);
      await extras.put({ ...now, albums: now.albums.filter((a) => a.id !== albumId) });
      changed();
    },
    [extras, changed],
  );

  /** Copies a picked picture in as the trip's cover; the previous copy is deleted. */
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
      return cover;
    },
    [extras, files, changed],
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
      await extras.put({ ...now, cover: { uri, fileName, setAt: Date.now() } });
      if (now.cover && now.cover.uri !== uri)
        await files.remove(now.cover.uri).catch(() => undefined);
      changed();
    },
    [extras, files, changed],
  );

  /** Removes a staged picture that was never adopted. */
  const dropStaged = useCallback(
    (uri: string) => files.remove(uri).catch(() => undefined),
    [files],
  );

  /** Back to the destination's photo (or the illustration). */
  const clearLocalCover = useCallback(
    async (tripId: string) => {
      const now = await extras.get(tripId);
      if (!now.cover) return;
      await extras.put({ ...now, cover: null });
      await files.remove(now.cover.uri).catch(() => undefined);
      changed();
    },
    [extras, changed, files],
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
  };
}
