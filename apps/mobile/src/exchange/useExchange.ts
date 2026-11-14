import type { Day, FileTrip, Itinerary, Trip, TripFile } from "@detour/shared";
import { useCallback } from "react";

import { useBackend } from "../api/BackendProvider";
import { NetworkError, call } from "../api/unwrap";
import { keys } from "../data/actions";
import { useData } from "../data/DataProvider";
import { useDocumentsInternals } from "../documents/DocumentsProvider";
import { type DocLink, type TripDocument, linkablePlaces, newDocumentId } from "../documents/model";
import {
  type ArchiveDocument,
  type ArchiveLink,
  type ReadArchive,
  ArchiveError,
  MAX_DOCUMENT_BYTES,
  buildArchive,
  exportFileName,
  readArchive,
} from "./archive";

// Trip export and import (ADR 028). The server writes and reads the trip itself; the phone adds
// the documents, builds the zip and shares it, and puts documents back after an import.

export type ExportOutcome = {
  trips: number;
  documents: number;
  /** Documents that could not be put in the file (unreadable or too large). */
  left: string[];
  shared: boolean;
  fileName: string;
};

export type ImportOutcome = {
  trips: { title: string; tripId: string }[];
  documents: number;
  /** Documents of the file that could not be restored, by title. */
  notRestored: string[];
};

export type DocumentSummary = { count: number; bytes: number };

function archiveLink(link: DocLink): ArchiveLink {
  switch (link.kind) {
    case "place":
      return { kind: "place", name: link.name, day: link.day };
    case "leg":
      return { kind: "leg", day: link.day, name: link.name };
    default:
      return link;
  }
}

/** The link in the new trip: a place is found again by its name (on its day first), a journey
 * becomes its day (imported plans have no journeys), and anything that no longer fits is the trip. */
export function restoreLink(link: ArchiveLink, days: Day[], duration: number): DocLink {
  const dayOk = (n: number | null): n is number => n !== null && n >= 1 && n <= duration;
  if (link.kind === "place") {
    const places = linkablePlaces(days);
    const found =
      places.find((p) => p.name === link.name && p.day === link.day) ??
      places.find((p) => p.name === link.name);
    if (found) return { kind: "place", key: found.key, name: found.name, day: found.day };
    return dayOk(link.day) ? { kind: "day", day: link.day } : { kind: "trip" };
  }
  if (link.kind === "day" || link.kind === "leg") {
    return dayOk(link.day) ? { kind: "day", day: link.day } : { kind: "trip" };
  }
  return { kind: "trip" };
}

export function useExchange() {
  const { state } = useBackend();
  const data = useData();
  const { store, exchange, changed } = useDocumentsInternals();
  const client = state.phase === "ready" ? state.connection.client : null;

  const need = useCallback(() => {
    if (!client) throw new NetworkError("The server is not connected yet.");
    return client;
  }, [client]);

  /** How many documents these trips hold on this phone, and their size. */
  const documentSummary = useCallback(
    async (tripIds: string[]): Promise<DocumentSummary> => {
      let count = 0;
      let bytes = 0;
      for (const id of tripIds) {
        for (const d of await store.list(id)) {
          count += 1;
          bytes += d.sizeBytes ?? 0;
        }
      }
      return { count, bytes };
    },
    [store],
  );

  /** One trip, or every trip when `tripIds` is "all": the file is built and handed to the share
   * sheet. */
  const exportTrips = useCallback(
    async (tripIds: string[] | "all", includeDocuments: boolean): Promise<ExportOutcome> => {
      const c = need();
      let ids: string[];
      let title: string | null = null;
      if (tripIds === "all") {
        const all = await call(c.GET("/v1/trips"));
        ids = [...all].reverse().map((t) => t.id); // oldest first, as the server's backup is
      } else {
        ids = tripIds;
      }
      const trips: FileTrip[] = [];
      for (const id of ids) {
        const one = await call(
          c.GET("/v1/trips/{trip_id}/export", { params: { path: { trip_id: id } } }),
        );
        trips.push(...one.trips);
      }
      if (tripIds !== "all") title = trips[0]?.title ?? null;
      const file: TripFile = {
        format: "detour-trip",
        format_version: 1,
        exported_at: new Date().toISOString(),
        trips,
      };
      const documents: ArchiveDocument[] = [];
      const left: string[] = [];
      if (includeDocuments) {
        for (const [tripIndex, tripId] of ids.entries()) {
          for (const d of await store.list(tripId)) {
            if ((d.sizeBytes ?? 0) > MAX_DOCUMENT_BYTES) {
              left.push(d.title);
              continue;
            }
            try {
              const bytes = await exchange.readBytes(d.uri);
              if (bytes.length > MAX_DOCUMENT_BYTES) {
                left.push(d.title);
                continue;
              }
              documents.push({
                tripIndex,
                title: d.title,
                category: d.category,
                link: archiveLink(d.link),
                date: d.date ?? null,
                notes: d.notes ?? null,
                fileName: d.fileName,
                mimeType: d.mimeType,
                bytes,
              });
            } catch {
              left.push(d.title); // the file is no longer on this phone
            }
          }
        }
      }
      const fileName = exportFileName(title, new Date());
      const uri = await exchange.saveShareable(fileName, buildArchive(file, documents));
      const shared = await exchange.share(uri);
      return { trips: trips.length, documents: documents.length, left, shared, fileName };
    },
    [need, store, exchange],
  );

  /** Reads a trip file from the phone. Throws ArchiveError for a file that is not one. */
  const readFile = useCallback(
    async (uri: string): Promise<ReadArchive> => {
      let bytes: Uint8Array;
      try {
        bytes = await exchange.readBytes(uri);
      } catch {
        throw new ArchiveError("This file could not be read.");
      }
      return readArchive(bytes);
    },
    [exchange],
  );

  /** Adds the file's trips as new trips, then their documents. Trips are all or nothing on the
   * server; a document that cannot be written is listed, the trip stays. */
  const importArchive = useCallback(
    async (read: ReadArchive): Promise<ImportOutcome> => {
      const c = need();
      const result = await call(c.POST("/v1/trips/import", { body: read.file }));
      data.forget(keys.trips);
      const made = result.trips.map((t) => ({ title: t.title, tripId: t.trip_id }));
      const notRestored = [...read.skipped];
      let restored = 0;
      const plans = new Map<number, { days: Day[]; duration: number }>();
      for (const doc of read.documents) {
        const target = result.trips[doc.tripIndex];
        if (!target) {
          notRestored.push(doc.title);
          continue;
        }
        try {
          if (!plans.has(doc.tripIndex)) {
            const trip: Trip = await call(
              c.GET("/v1/trips/{trip_id}", { params: { path: { trip_id: target.trip_id } } }),
            );
            const plan: Itinerary | null = trip.selected_itinerary_id
              ? await call(
                  c.GET("/v1/itineraries/{itinerary_id}", {
                    params: { path: { itinerary_id: trip.selected_itinerary_id } },
                  }),
                )
              : null;
            plans.set(doc.tripIndex, { days: plan?.days ?? [], duration: trip.duration_days });
          }
          const where = plans.get(doc.tripIndex) as { days: Day[]; duration: number };
          const id = newDocumentId();
          const uri = await exchange.keepBytes(doc.bytes, target.trip_id, id, doc.fileName);
          const record: TripDocument = {
            id,
            tripId: target.trip_id,
            title: doc.title,
            category: doc.category,
            link: restoreLink(doc.link, where.days, where.duration),
            fileName: doc.fileName,
            mimeType: doc.mimeType,
            sizeBytes: doc.bytes.length,
            uri,
            createdAt: Date.now(),
            date: doc.date,
            notes: doc.notes,
          };
          await store.put(record);
          restored += 1;
        } catch {
          notRestored.push(doc.title);
        }
      }
      if (restored > 0) changed();
      return { trips: made, documents: restored, notRestored };
    },
    [need, data, exchange, store, changed],
  );

  return {
    connected: client !== null,
    pick: exchange.pick,
    documentSummary,
    exportTrips,
    readFile,
    importArchive,
  };
}
