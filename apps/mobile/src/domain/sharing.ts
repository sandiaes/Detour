// Sharing a trip with a linked person (ADR 034, step 3): how members and people read on screen.
import type { Trip, TripMember, components } from "@detour/shared";

export type LinkedPerson = components["schemas"]["LinkedPerson"];

/** A person's name, or a plain stand-in when they set none. */
export function personName(name: string | null | undefined): string {
  return name && name.trim() ? name : "Someone without a name";
}

/** The other members of a trip (not you). */
export function otherMembers(trip: Trip): TripMember[] {
  return (trip.members ?? []).filter((m) => !m.you);
}

/** "With Ana", "With Ana and Luis"; null for a trip of your own. */
export function sharedLine(trip: Trip): string | null {
  const names = otherMembers(trip).map((m) => personName(m.name));
  if (names.length === 0) return null;
  if (names.length === 1) return `With ${names[0]}`;
  return `With ${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** The trip's owner, when it is someone else. */
export function ownerOf(trip: Trip): TripMember | null {
  return (trip.members ?? []).find((m) => m.role === "owner" && !m.you) ?? null;
}

/** Linked people who are not on the trip yet. */
export function canShareWith(trip: Trip, people: LinkedPerson[]): LinkedPerson[] {
  const on = new Set((trip.members ?? []).map((m) => m.person_id));
  return people.filter((p) => !on.has(p.person_id));
}
