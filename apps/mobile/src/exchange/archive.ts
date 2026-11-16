import type { TripFile } from "@detour/shared";
import { strFromU8, strToU8, unzipSync, zipSync, type Zippable } from "fflate";

import { MAX_ALBUM_NAME, normaliseAlbumUrl } from "../documents/extras";
import { CATEGORIES, type DocCategory } from "../documents/model";

// The trip file (ADR 028): a zip named *.detour holding trip.json (what the server exports) and,
// when the user asks, documents.json with the files under documents/, and albums.json with the
// trips' album links (ADR 031). This module only builds and
// reads that zip; it never touches the device or the network.

export const FORMAT = "detour-trip";
export const FORMAT_VERSION = 1;
export const MAX_ARCHIVE_BYTES = 50 * 1024 * 1024;
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const MAX_JSON_BYTES = 8 * 1024 * 1024;
const MAX_DOCUMENTS = 500;

/** What a document is about, by name and day (our identifiers do not leave the phone). */
export type ArchiveLink =
  | { kind: "trip" }
  | { kind: "day"; day: number }
  | { kind: "place"; name: string; day: number | null }
  | { kind: "leg"; day: number; name: string };

export type ArchiveDocument = {
  /** The position of the document's trip in `trips` of trip.json. */
  tripIndex: number;
  title: string;
  category: DocCategory;
  link: ArchiveLink;
  date: string | null;
  notes: string | null;
  fileName: string;
  mimeType: string;
  bytes: Uint8Array;
};

/** A link to the user's own photo album (ADR 031): only the link travels, never photos. */
export type ArchiveAlbum = { tripIndex: number; name: string; url: string };

const MAX_ARCHIVE_ALBUMS = 500;

export class ArchiveError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ArchiveError";
  }
}

type DocumentRecord = {
  trip_index: number;
  title: string;
  category: string;
  link: ArchiveLink;
  date: string | null;
  notes: string | null;
  file_name: string;
  mime_type: string;
  path: string;
};

function extensionOf(name: string): string {
  const match = /\.[A-Za-z0-9]{1,8}$/.exec(name);
  return match ? match[0].toLowerCase() : "";
}

export function buildArchive(
  file: TripFile,
  documents: ArchiveDocument[],
  albums: ArchiveAlbum[] = [],
): Uint8Array {
  const entries: Zippable = { "trip.json": strToU8(JSON.stringify(file, null, 1)) };
  if (albums.length > 0) {
    entries["albums.json"] = strToU8(
      JSON.stringify(
        {
          format: "detour-albums",
          format_version: 1,
          albums: albums.map((a) => ({ trip_index: a.tripIndex, name: a.name, url: a.url })),
        },
        null,
        1,
      ),
    );
  }
  if (documents.length > 0) {
    const records: DocumentRecord[] = documents.map((d, n) => {
      const path = `documents/${n + 1}${extensionOf(d.fileName)}`;
      // PDFs and pictures are compressed already: stored as they are.
      entries[path] = [d.bytes, { level: 0 }];
      return {
        trip_index: d.tripIndex,
        title: d.title,
        category: d.category,
        link: d.link,
        date: d.date,
        notes: d.notes,
        file_name: d.fileName,
        mime_type: d.mimeType,
        path,
      };
    });
    entries["documents.json"] = strToU8(
      JSON.stringify(
        { format: "detour-documents", format_version: 1, documents: records },
        null,
        1,
      ),
    );
  }
  return zipSync(entries, { level: 6 });
}

export type ReadArchive = {
  file: TripFile;
  documents: ArchiveDocument[];
  /** Album links (ADR 031); a link that is not an https address is dropped. */
  albums: ArchiveAlbum[];
  /** Documents the file names but could not give (missing, too large or unreadable). */
  skipped: string[];
};

function parseJson(bytes: Uint8Array, what: string): unknown {
  try {
    return JSON.parse(strFromU8(bytes));
  } catch {
    throw new ArchiveError(`${what} in this file is damaged.`);
  }
}

const isLink = (l: unknown): l is ArchiveLink => {
  if (typeof l !== "object" || l === null) return false;
  const v = l as Record<string, unknown>;
  switch (v.kind) {
    case "trip":
      return true;
    case "day":
      return typeof v.day === "number";
    case "place":
      return typeof v.name === "string" && (v.day === null || typeof v.day === "number");
    case "leg":
      return typeof v.day === "number" && typeof v.name === "string";
    default:
      return false;
  }
};

/** Reads a .detour file. Throws ArchiveError, in words, for anything that is not a trip file. */
export function readArchive(bytes: Uint8Array): ReadArchive {
  if (bytes.length > MAX_ARCHIVE_BYTES) {
    throw new ArchiveError("This file is larger than 50 MB, which a trip file never is.");
  }
  let entries: Record<string, Uint8Array>;
  try {
    // Entries claiming to expand beyond what is allowed are not unpacked at all.
    entries = unzipSync(bytes, {
      filter: (f) =>
        f.originalSize <= (f.name.endsWith(".json") ? MAX_JSON_BYTES : MAX_DOCUMENT_BYTES),
    });
  } catch {
    throw new ArchiveError("This is not a Detour trip file.");
  }
  const tripJson = entries["trip.json"];
  if (!tripJson) throw new ArchiveError("This is not a Detour trip file.");
  const parsed = parseJson(tripJson, "The trip") as Partial<TripFile> | null;
  if (!parsed || parsed.format !== FORMAT || !Array.isArray(parsed.trips)) {
    throw new ArchiveError("This is not a Detour trip file.");
  }
  if (typeof parsed.format_version !== "number" || parsed.format_version < 1) {
    throw new ArchiveError("This is not a Detour trip file.");
  }
  if (parsed.format_version > FORMAT_VERSION) {
    throw new ArchiveError(
      "This file was made by a newer version of Detour. Update the app to open it.",
    );
  }
  const file = parsed as TripFile;

  const documents: ArchiveDocument[] = [];
  const skipped: string[] = [];
  const list = entries["documents.json"];
  if (list) {
    const records = (parseJson(list, "The list of documents") as { documents?: unknown })
      ?.documents;
    if (!Array.isArray(records)) throw new ArchiveError("The list of documents is damaged.");
    for (const r of records.slice(0, MAX_DOCUMENTS) as Partial<DocumentRecord>[]) {
      const title = typeof r.title === "string" && r.title.trim() ? r.title.trim() : "Document";
      const path =
        typeof r.path === "string" && /^documents\/[A-Za-z0-9._-]+$/.test(r.path) ? r.path : null;
      const data = path ? entries[path] : undefined;
      if (
        typeof r.trip_index !== "number" ||
        r.trip_index < 0 ||
        r.trip_index >= file.trips.length ||
        !data ||
        !isLink(r.link)
      ) {
        skipped.push(title);
        continue;
      }
      documents.push({
        tripIndex: r.trip_index,
        title: title.slice(0, 120),
        category: (CATEGORIES as readonly string[]).includes(r.category ?? "")
          ? (r.category as DocCategory)
          : "other",
        link: r.link,
        date: typeof r.date === "string" ? r.date : null,
        notes: typeof r.notes === "string" ? r.notes.slice(0, 500) : null,
        fileName: typeof r.file_name === "string" ? r.file_name : "document",
        mimeType: typeof r.mime_type === "string" ? r.mime_type : "application/octet-stream",
        bytes: data,
      });
    }
    if (records.length > MAX_DOCUMENTS) skipped.push(`${records.length - MAX_DOCUMENTS} more`);
  }
  const albums: ArchiveAlbum[] = [];
  const albumList = entries["albums.json"];
  if (albumList) {
    const records = (parseJson(albumList, "The list of albums") as { albums?: unknown })?.albums;
    if (Array.isArray(records)) {
      for (const r of records.slice(0, MAX_ARCHIVE_ALBUMS) as Record<string, unknown>[]) {
        const url = typeof r?.url === "string" ? normaliseAlbumUrl(r.url) : null;
        const tripIndex = r?.trip_index;
        if (
          !url ||
          typeof tripIndex !== "number" ||
          tripIndex < 0 ||
          tripIndex >= file.trips.length
        ) {
          continue;
        }
        const name = typeof r.name === "string" && r.name.trim() ? r.name.trim() : "Trip album";
        albums.push({ tripIndex, name: name.slice(0, MAX_ALBUM_NAME), url });
      }
    }
  }
  return { file, documents, albums, skipped };
}

/** What a file holds, for the screen that asks before importing. */
export function describeFile(read: ReadArchive): {
  trips: { title: string; destination: string; days: number; stops: number; past: boolean }[];
  documents: number;
  albums: number;
} {
  return {
    trips: read.file.trips.map((t) => ({
      title: t.title,
      destination: t.destination.name,
      days: t.duration_days,
      stops:
        t.status === "past"
          ? (t.visits ?? []).length
          : (t.days ?? []).reduce((n, d) => n + (d.items ?? []).length, 0),
      past: t.status === "past",
    })),
    documents: read.documents.length,
    albums: read.albums.length,
  };
}

/** A safe name for the file the user shares: "Detour-Hallstatt-2026-11-14.detour". */
export function exportFileName(title: string | null, date: Date): string {
  const slug = (title ?? "backup")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return `Detour-${slug || "trip"}-${date.toISOString().slice(0, 10)}.detour`;
}
