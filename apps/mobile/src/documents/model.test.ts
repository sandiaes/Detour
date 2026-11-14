import type { Day } from "@detour/shared";

import { makeItinerary } from "../testing/fixtures";
import {
  normaliseCategory,
  type TripDocument,
  fileLine,
  groupByCategory,
  isAccepted,
  linkLabel,
  linkableLegs,
  linkablePlaces,
  mimeFromName,
  newDocumentId,
  placeKey,
  titleFromFileName,
} from "./model";

const doc = (over: Partial<TripDocument>): TripDocument => ({
  id: "d",
  tripId: "t",
  title: "Doc",
  category: "other",
  link: { kind: "trip" },
  fileName: "a.pdf",
  mimeType: "application/pdf",
  sizeBytes: 1000,
  uri: "file:///a.pdf",
  createdAt: 1,
  ...over,
});

test("a title is made from the file name", () => {
  expect(titleFromFileName("Train_ticket-Vienna.pdf")).toBe("Train ticket Vienna");
  expect(titleFromFileName("IMG 2041.JPG")).toBe("IMG 2041");
  expect(titleFromFileName(".pdf")).toBe("Document");
});

test("only PDFs and pictures are kept; types are guessed from the name when missing", () => {
  expect(isAccepted("application/pdf")).toBe(true);
  expect(isAccepted("image/heic")).toBe(true);
  expect(isAccepted("application/zip")).toBe(false);
  expect(mimeFromName("Ticket.PDF")).toBe("application/pdf");
  expect(mimeFromName("scan.jpeg")).toBe("image/jpeg");
  expect(mimeFromName("pass.pkpass")).toBe("application/octet-stream");
});

test("the file line says the kind and the size, or only the kind when the size is unknown", () => {
  expect(fileLine({ mimeType: "application/pdf", sizeBytes: 245_000 })).toBe("PDF · 245.0 kB");
  expect(fileLine({ mimeType: "image/png", sizeBytes: null })).toBe("Image");
});

test("a place is keyed by the imported place, else the user's place, else its name", () => {
  expect(placeKey({ place_id: "p", user_place_id: null, display_name: "X" })).toBe("place:p");
  expect(placeKey({ place_id: null, user_place_id: "u", display_name: "X" })).toBe("user:u");
  expect(placeKey({ place_id: null, user_place_id: null, display_name: "X" })).toBe("name:X");
});

test("links read as words, with the date when the trip has one", () => {
  expect(linkLabel({ kind: "trip" }, null)).toBe("Whole trip");
  expect(linkLabel({ kind: "day", day: 2 }, "2027-05-01")).toBe("Day 2 · Sun 2 May");
  expect(linkLabel({ kind: "day", day: 2 }, null)).toBe("Day 2");
  expect(linkLabel({ kind: "place", key: "k", name: "Belvedere", day: 1 }, null)).toBe(
    "Belvedere · day 1",
  );
  expect(linkLabel({ kind: "leg", day: 2, name: "Graz" }, null)).toBe("Journey to Graz · day 2");
});

test("the places of a plan, once each in day order, and its journeys", () => {
  const days = makeItinerary("essentials").days as Day[];
  const places = linkablePlaces(days);
  expect(places[0]).toEqual({ key: "name:Schönbrunn Palace", name: "Schönbrunn Palace", day: 1 });
  expect(places.map((p) => p.name)).toContain("Gasthaus Zum Test");
  expect(new Set(places.map((p) => p.key)).size).toBe(places.length);
  expect(linkableLegs(days)).toEqual([{ day: 2, name: "Graz", from: "Vienna" }]);
});

test("documents are grouped by kind in a fixed order, newest first", () => {
  const groups = groupByCategory([
    doc({ id: "1", category: "other", createdAt: 1 }),
    doc({ id: "2", category: "ticket", createdAt: 1 }),
    doc({ id: "3", category: "ticket", createdAt: 5 }),
  ]);
  expect(groups.map((g) => g.category)).toEqual(["ticket", "other"]);
  expect(groups[0]?.docs.map((d) => d.id)).toEqual(["3", "2"]);
});

test("insurance, a kind until 2026-11-14, now reads as other", () => {
  expect(normaliseCategory("insurance")).toBe("other");
  expect(normaliseCategory("ticket")).toBe("ticket");
});

test("identifiers are unique enough on one device", () => {
  let n = 0;
  const id = newDocumentId(
    () => (n++ % 10) / 10,
    () => 255,
  );
  expect(id).toMatch(/^ff-[0-9a-f]{16}$/);
  expect(newDocumentId()).not.toBe(newDocumentId());
});
