import type { Day, Item } from "@detour/shared";

import { MODE_LABEL } from "../domain/transport";
import { formatBytes, formatDayLabel } from "../util/format";

// Trip documents (ADR 023): tickets, bookings, transport and other documents, kept on the
// device only. A document belongs to a trip and can be about the whole trip, a day, a place of the
// plan or the journey that starts a day at a new base city. Links name the place as it was when
// linked, so they still read correctly after the plan changes or the trip becomes past.

export const CATEGORIES = ["ticket", "booking", "transport", "other"] as const;
export type DocCategory = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<DocCategory, string> = {
  ticket: "Ticket",
  booking: "Booking",
  transport: "Transport",
  other: "Other",
};

export const CATEGORY_GROUP: Record<DocCategory, string> = {
  ticket: "Tickets",
  booking: "Bookings",
  transport: "Transport",
  other: "Other documents",
};

export type DocLink =
  | { kind: "trip" }
  | { kind: "day"; day: number }
  | { kind: "place"; key: string; name: string; day: number | null }
  | { kind: "leg"; day: number; name: string };

export type TripDocument = {
  id: string;
  tripId: string;
  title: string;
  category: DocCategory;
  link: DocLink;
  fileName: string;
  mimeType: string;
  sizeBytes: number | null;
  /** The copy in the app's private storage. */
  uri: string;
  createdAt: number;
  /** The date the document is about (a flight's day, a check-in), ISO; optional. Documents saved
   * before this field existed have none. */
  date?: string | null;
  /** The user's own note, at most `NOTES_MAX` characters; optional. */
  notes?: string | null;
};

export const NOTES_MAX = 500;

/** Insurance was a kind until 2026-11-14 (owner request); a document saved under it reads as
 * "other" now, so nothing on the phone is lost or left without a kind. */
export function normaliseCategory(category: string): DocCategory {
  return (CATEGORIES as readonly string[]).includes(category) ? (category as DocCategory) : "other";
}

/** One line under each kind on the empty Documents tab: what belongs there. */
export const CATEGORY_HELP: Record<DocCategory, string> = {
  ticket: "Entry and activity tickets",
  booking: "Hotels, tables, tours",
  transport: "Flights, trains, buses",
  other: "Visas, itineraries, more",
};

export type DocSort = "newest" | "oldest" | "title";
export const SORT_LABEL: Record<DocSort, string> = {
  newest: "Newest first",
  oldest: "Oldest first",
  title: "Title, A to Z",
};

/** The documents in the order asked for; ties are broken by identifier so it is stable. */
export function sortDocuments(docs: TripDocument[], sort: DocSort): TripDocument[] {
  const by =
    sort === "title"
      ? (a: TripDocument, b: TripDocument) => a.title.localeCompare(b.title)
      : sort === "oldest"
        ? (a: TripDocument, b: TripDocument) => a.createdAt - b.createdAt
        : (a: TripDocument, b: TripDocument) => b.createdAt - a.createdAt;
  return [...docs].sort((a, b) => by(a, b) || a.id.localeCompare(b.id));
}

/** A file the user picked, before it is copied into the app's storage. */
export type PickedFile = { uri: string; name: string; mimeType: string; size: number | null };

/** Files Detour keeps: PDFs and pictures, which every phone can show. */
export const ACCEPTED_TYPES = ["application/pdf", "image/*"];

export function isAccepted(mimeType: string): boolean {
  return mimeType === "application/pdf" || mimeType.startsWith("image/");
}

/** The MIME type from a file name, for pickers that report none. */
export function mimeFromName(name: string): string {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  const known: Record<string, string> = {
    pdf: "application/pdf",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    png: "image/png",
    heic: "image/heic",
    webp: "image/webp",
  };
  return known[ext] ?? "application/octet-stream";
}

/** "Train_ticket-Vienna.pdf" -> "Train ticket Vienna". */
export function titleFromFileName(name: string): string {
  const base = name.replace(/\.[^./]+$/, "");
  const words = base.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return words.slice(0, 80) || "Document";
}

/** "PDF · 240.0 kB", "Image · 1.2 MB". */
export function fileLine(doc: Pick<TripDocument, "mimeType" | "sizeBytes">): string {
  const kind =
    doc.mimeType === "application/pdf" ? "PDF" : isAccepted(doc.mimeType) ? "Image" : "File";
  return doc.sizeBytes != null ? `${kind} · ${formatBytes(doc.sizeBytes)}` : kind;
}

/** A stable key for the place of a plan item: the imported place, the user's place, or the name. */
export function placeKey(item: Pick<Item, "place_id" | "user_place_id" | "display_name">): string {
  if (item.place_id) return `place:${item.place_id}`;
  if (item.user_place_id) return `user:${item.user_place_id}`;
  return `name:${item.display_name}`;
}

/** What a document is about, in words. */
const ENTERED_LEG = new RegExp(`^(${Object.values(MODE_LABEL).join("|")}) to `);

export function linkLabel(link: DocLink, startDate: string | null): string {
  switch (link.kind) {
    case "trip":
      return "Whole trip";
    case "day":
      return formatDayLabel(startDate, link.day);
    case "place":
      return link.day ? `${link.name} · day ${link.day}` : link.name;
    case "leg":
      // A leg the user entered is already named by its mode ("Train to Florence", ADR 032).
      return ENTERED_LEG.test(link.name)
        ? `${link.name} · day ${link.day}`
        : `Journey to ${link.name} · day ${link.day}`;
  }
}

/** The places of a plan a document can be about: its visits and meals, in day order, once each. */
export function linkablePlaces(days: Day[]): { key: string; name: string; day: number }[] {
  const seen = new Set<string>();
  const out: { key: string; name: string; day: number }[] = [];
  for (const day of [...days].sort((a, b) => a.day_index - b.day_index)) {
    for (const item of day.items) {
      // A transport leg is not a place: its documents link to it as a journey (ADR 032).
      if (item.type === "free_time" || item.type === "transport") continue;
      const key = placeKey(item);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ key, name: item.display_name, day: day.day_index });
    }
  }
  return out;
}

export type LinkableLeg = { day: number; name: string; from: string | null; entered?: boolean };

/** The journeys of a plan: each day that starts at a new base city, and each transport leg the
 * user entered (ADR 032), named as it reads in the plan ("Train to Florence"). */
export function linkableLegs(days: Day[]): LinkableLeg[] {
  const out: LinkableLeg[] = [];
  for (const d of [...days].sort((a, b) => a.day_index - b.day_index)) {
    if (d.arrival && !d.arrival.covered_by_item_id) {
      out.push({
        day: d.day_index,
        name: d.base_city_name ?? `day ${d.day_index}`,
        from: d.arrival.from_base_city_name ?? null,
      });
    }
    for (const item of d.items) {
      if (item.type !== "transport" || !item.transport) continue;
      out.push({
        day: d.day_index,
        name: item.display_name,
        from: item.transport.from_name,
        entered: true,
      });
    }
  }
  return out;
}

/** Documents grouped by category in a fixed order, newest first within a group. */
export function groupByCategory(
  docs: TripDocument[],
): { category: DocCategory; docs: TripDocument[] }[] {
  return CATEGORIES.map((category) => ({
    category,
    docs: docs
      .filter((d) => d.category === category)
      .sort((a, b) => b.createdAt - a.createdAt || a.id.localeCompare(b.id)),
  })).filter((g) => g.docs.length > 0);
}

/** A random identifier; documents never leave the device, so uniqueness on it is enough. */
export function newDocumentId(
  random: () => number = Math.random,
  now: () => number = Date.now,
): string {
  const r = () =>
    Math.floor(random() * 0x100000000)
      .toString(16)
      .padStart(8, "0");
  return `${now().toString(16)}-${r()}${r()}`;
}
