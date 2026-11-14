import { type ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";

import type { DocumentFiles } from "./files";
import {
  type DocCategory,
  type DocLink,
  type PickedFile,
  type TripDocument,
  newDocumentId,
} from "./model";
import type { DocumentStore } from "./store";

type Value = { store: DocumentStore; files: DocumentFiles; version: number; changed: () => void };

const DocumentsContext = createContext<Value | null>(null);

export function DocumentsProvider({
  store,
  files,
  children,
}: {
  store: DocumentStore;
  files: DocumentFiles;
  children: ReactNode;
}) {
  const [version, setVersion] = useState(0);
  const changed = useCallback(() => setVersion((v) => v + 1), []);
  return (
    <DocumentsContext.Provider value={{ store, files, version, changed }}>
      {children}
    </DocumentsContext.Provider>
  );
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

export type DocumentFields = { title: string; category: DocCategory; link: DocLink };

export function useDocumentActions() {
  const { store, files, changed } = useDocumentsContext();

  const add = useCallback(
    async (tripId: string, picked: PickedFile, fields: DocumentFields): Promise<TripDocument> => {
      const id = newDocumentId();
      const uri = await files.keep(picked, tripId, id);
      const doc: TripDocument = {
        id,
        tripId,
        ...fields,
        title: fields.title.trim(),
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
      await store.put({ ...doc, ...fields, title: fields.title.trim() });
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

  /** Called when a trip is deleted: its documents and their files go too. */
  const removeTrip = useCallback(
    async (tripId: string) => {
      const gone = await store.removeTrip(tripId);
      await Promise.all(gone.map((d) => files.remove(d.uri).catch(() => undefined)));
      if (gone.length) changed();
    },
    [files, store, changed],
  );

  return { pick: files.pick, open: files.open, add, update, remove, removeTrip };
}
