// Times of day typed or picked by the user: "9:30", "09.30" or the wheel's "09:30".

/** "9:30" or "09:30" -> "09:30"; null when it is not a time of day. */
export function parseClock(text: string): string | null {
  const m = /^(\d{1,2})[:.](\d{2})$/.exec(text.trim());
  if (!m) return null;
  const [h, min] = [Number(m[1]), Number(m[2])];
  if (h > 23 || min > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

/** Hours and minutes to "HH:MM", wrapping past midnight in either direction. */
export function clockFrom(hours: number, minutes: number): string {
  const total = (((hours * 60 + minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** The number of a unit typed as hours: "1.5" or "1,5" -> 90 minutes; null when it is not a
 * length of 1 minute to 24 hours. */
export function minutesFromHours(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (!/^\d{1,2}(?:\.\d{1,2})?$/.test(t)) return null;
  const minutes = Math.round(Number(t) * 60);
  return minutes >= 1 && minutes <= 1440 ? minutes : null;
}

/** Minutes as the hours a field shows: 90 -> "1.5", 120 -> "2", 75 -> "1.25". */
export function hoursText(minutes: number): string {
  return String(Math.round((minutes / 60) * 100) / 100);
}
