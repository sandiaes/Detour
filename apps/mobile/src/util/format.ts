// Plain formatting helpers. No Intl: the output must not depend on the device locale or the
// JavaScript engine, so the tests are exact. The interface is English only (no i18n in Phase 5).

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** 45 -> "45 min", 90 -> "1 h 30 min", 120 -> "2 h". */
export function formatMinutes(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest === 0 ? `${h} h` : `${h} h ${rest} min`;
}

/** Seconds, rounded up to whole minutes ("1 min" for anything under a minute, never "0 min"). */
export function formatSeconds(seconds: number): string {
  return formatMinutes(Math.max(1, Math.ceil(seconds / 60)));
}

export function formatMeters(meters: number): string {
  if (meters < 1000) return `${Math.round(meters / 10) * 10 || 10} m`;
  const km = meters / 1000;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}

/** "09:30:00" or "09:30" -> "09:30". */
export function formatClock(time: string | null | undefined): string | null {
  if (!time) return null;
  return time.slice(0, 5);
}

export function parseIsoDate(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const [y, m, d] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(y, m - 1, d));
  // Reject 2027-02-31 and the like: the Date constructor rolls over instead of failing.
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) {
    return null;
  }
  return date;
}

export function isValidIsoDate(iso: string): boolean {
  return parseIsoDate(iso) !== null;
}

/** "2027-05-01" -> "Sat 1 May 2027". Returns the input unchanged if it is not a date. */
export function formatDate(iso: string, withYear = true): string {
  const date = parseIsoDate(iso);
  if (!date) return iso;
  const base = `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
  return withYear ? `${base} ${date.getUTCFullYear()}` : base;
}

/** "1 May – 3 May 2027", or "3 days" without dates. */
export function formatTripSpan(start: string | null, end: string | null, days: number): string {
  const length = `${days} ${days === 1 ? "day" : "days"}`;
  if (!start || !end) return length;
  return `${formatDate(start, false)} to ${formatDate(end)} · ${length}`;
}

export function pluralise(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "5 min ago" style age of a cached copy, for the offline notice. */
export function formatAge(savedAtMs: number, nowMs: number): string {
  const minutes = Math.max(0, Math.floor((nowMs - savedAtMs) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${pluralise(minutes, "minute")} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${pluralise(hours, "hour")} ago`;
  return `${pluralise(Math.floor(hours / 24), "day")} ago`;
}

/** "Day 2 · Sun 2 May" with a start date, "Day 2" without one. */
export function formatDayLabel(startDate: string | null, day: number): string {
  const start = startDate ? parseIsoDate(startDate) : null;
  if (!start) return `Day ${day}`;
  const date = new Date(start.getTime() + (day - 1) * 86_400_000);
  return `Day ${day} · ${formatDate(date.toISOString().slice(0, 10), false)}`;
}

/** "812 bytes", "4.5 kB", "1.2 MB" (powers of 1000). */
export function formatBytes(bytes: number): string {
  if (bytes < 1000) return `${bytes} ${bytes === 1 ? "byte" : "bytes"}`;
  if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(1)} kB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}
