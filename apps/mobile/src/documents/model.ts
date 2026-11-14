import type { Day, Item } from "@detour/shared";

import { formatBytes, formatDayLabel } from "../util/format";

// Trip documents (ADR 023): tickets, bookings, transport documents and insurance, kept on the
// device only. A document belongs to a trip and can be about the whole trip, a day, a place of the
// plan or the journey that starts a day at a new base city. Links name the place as it was when
// linked, so they still read correctly after the plan changes or the trip becomes past.

export const CATEGORIES = ["ticket", "booking", "transport", "insurance", "other"] as const;
export type DocCategory = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<DocCategory, string> = {
  ticket: "Ticket",
  booking: "Booking",
  transport: "Transport",
  insurance: "Insurance",
  other: "Other",
};

export const CATEGORY_GROUP: Record<DocCategory, string> = {
  ticket: "Tickets",
  booking: "Bookings",
  transport: "Transport",
  insurance: "Insurance",
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
};

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
export function linkLabel(link: DocLink, startDate: string | null): string {
  switch (link.kind) {
    case "trip":
      return "Whole trip";
    case "day":
      return formatDayLabel(startDate, link.day);
    case "place":
      return link.day ? `${link.name} · day ${link.day}` : link.name;
    case "leg":
      return `Journey to ${link.name} · day ${link.day}`;
  }
}

/** The places of a plan a document can be about: its visits and meals, in day order, once each. */
export function linkablePlaces(days: Day[]): { key: string; name: string; day: number }[] {
  const seen = new Set<string>();
  const out: { key: string; name: string; day: number }[] = [];
  for (const day of [...days].sort((a, b) => a.day_index - b.day_index)) {
    for (const item of day.items) {
      if (item.type === "free_time") continue;
      const key = placeKey(item);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ key, name: item.display_name, day: day.day_index });
    }
  }
  return out;
}

/** The journeys of a plan: each day that starts at a new base city. */
export function linkableLegs(days: Day[]): { day: number; name: string; from: string | null }[] {
  return [...days]
    .sort((a, b) => a.day_index - b.day_index)
    .filter((d) => d.arrival)
    .map((d) => ({
      day: d.day_index,
      name: d.base_city_name ?? `day ${d.day_index}`,
      from: d.arrival?.from_base_city_name ?? null,
    }));
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
