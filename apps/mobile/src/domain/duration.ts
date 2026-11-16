import type { Day, Item } from "@detour/shared";

import { formatMinutes } from "../util/format";
import { clockOf, minutesOf } from "./itinerary";

// The length of a stop: what the user may type, and what a new length would run into.

export const MAX_STAY_MINUTES = 1440;
/** The usual end of a day (ADR 026, proposed): a stop that ends later gets a warning, not a block. */
export const DAY_END_MINUTES = 20 * 60;
/** The usual start of a day (ADR 026, proposed). */
export const DAY_START_MINUTES = 9 * 60;

/**
 * The suggested start of a new stop on `day`: right after the last timed stop (and its trip to the
 * next one, when it has one), or the start of the day when nothing is timed yet (owner request,
 * 2026-11-16: not the earliest gap, which could land before the stops already there). Free time is
 * not a stop. `except` leaves one stop out (the one being moved).
 */
export function firstAvailableTime(
  day: Day | undefined,
  _minutes: number,
  except?: string,
): string {
  let at = DAY_START_MINUTES;
  for (const i of day?.items ?? []) {
    if (i.id === except || i.type === "free_time") continue;
    const end = minutesOf(i.end_time);
    if (minutesOf(i.start_time) === null || end === null) continue;
    at = Math.max(at, end + (i.transfer ? Math.ceil(i.transfer.seconds / 60) : 0));
  }
  return clockOf(Math.min(at, 23 * 60 + 59));
}

/**
 * Minutes from what the user typed: "90", "1:30", "1h30", "1 h 30 min", "2h", "45 min". Null when
 * it is not a length of 1 minute to 24 hours.
 */
export function parseMinutes(text: string): number | null {
  const t = text.trim().toLowerCase();
  if (!t) return null;
  let minutes: number | null = null;
  const plain = /^(\d{1,4})(?:\s*(?:m|min|mins|minutes?))?$/.exec(t);
  const clock = /^(\d{1,2}):(\d{2})$/.exec(t);
  const hours =
    /^(\d{1,2})\s*(?:h|hr|hrs|hours?)(?:\s*(\d{1,2})\s*(?:m|min|mins|minutes?)?)?$/.exec(t);
  if (plain) minutes = Number(plain[1]);
  else if (clock) minutes = Number(clock[1]) * 60 + Number(clock[2]);
  else if (hours) minutes = Number(hours[1]) * 60 + Number(hours[2] ?? 0);
  return minutes !== null && minutes >= 1 && minutes <= MAX_STAY_MINUTES ? minutes : null;
}

export type DurationCheck = {
  /** "error": it runs into the next stop and cannot be saved; "warning": it can be saved. */
  level: "error" | "warning";
  text: string;
};

/**
 * What a new length for `item` would run into, in its own day: the next timed stop (an overlap is
 * refused by the server, so it blocks), the time to get there (a warning), and the end of the day
 * (a warning). Null when it fits or the stop has no start time.
 */
export function checkDuration(
  day: Day,
  item: Item,
  minutes: number,
  /** A new start time ("HH:MM") being tried instead of the stop's own. */
  newStart?: string | null,
): DurationCheck | null {
  const start = minutesOf(newStart ?? item.start_time);
  if (start === null) return null;
  const end = start + minutes;
  // A start that falls inside the stop before it is refused by the server too.
  const before = day.items
    .filter((i) => i.id !== item.id && i.type !== "free_time" && minutesOf(i.end_time) !== null)
    .filter((i) => (minutesOf(i.start_time) ?? Infinity) < start)
    .sort((a, b) => (minutesOf(b.end_time) as number) - (minutesOf(a.end_time) as number))[0];
  if (before && (minutesOf(before.end_time) as number) > start) {
    return {
      level: "error",
      text: `Starts at ${clockOf(start)}, before ${before.display_name} ends at ${clockOf(minutesOf(before.end_time) as number)}. Choose a later start or move that stop first.`,
    };
  }
  const next = day.items
    .filter((i) => i.id !== item.id && i.type !== "free_time" && minutesOf(i.start_time) !== null)
    .filter((i) => (minutesOf(i.start_time) as number) >= start)
    .sort((a, b) => (minutesOf(a.start_time) as number) - (minutesOf(b.start_time) as number))[0];
  if (next) {
    const nextStart = minutesOf(next.start_time) as number;
    if (nextStart < end) {
      return {
        level: "error",
        text: `Ends at ${clockOf(end)}, after ${next.display_name} starts at ${clockOf(nextStart)}. Choose a shorter stay or move that stop first.`,
      };
    }
    // The transfer is to the stop that follows in the plan; only its time to that one is known.
    const followsInPlan = newStart == null && item.transfer?.to_item_id === next.id;
    if (followsInPlan && item.transfer) {
      const travel = Math.ceil(item.transfer.seconds / 60);
      if (end + travel > nextStart) {
        return {
          level: "warning",
          text: `Only ${formatMinutes(nextStart - end)} is left before ${next.display_name} at ${clockOf(nextStart)}, and the trip there takes ${formatMinutes(travel)}.`,
        };
      }
    }
  }
  if (end > DAY_END_MINUTES) {
    return {
      level: "warning",
      text: `Ends at ${clockOf(end % 1440)}, after the usual end of the day at ${clockOf(DAY_END_MINUTES)}.`,
    };
  }
  return null;
}
