// Turns the typed client's { data, error, response } results into values or typed errors, so a
// screen only has to tell three situations apart: the server answered with an error (ApiError),
// the server could not be reached (NetworkError), or success.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
    message: string,
    readonly body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** No answer: offline, DNS, refused, timeout. The cached copy, if any, is shown instead. */
export class NetworkError extends Error {
  constructor(message = "The server could not be reached.") {
    super(message);
    this.name = "NetworkError";
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

export async function call<T>(request: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await request;
  } catch (e) {
    // fetch rejects with a TypeError on network failure and an AbortError on our timeout.
    throw new NetworkError(e instanceof Error ? e.message : undefined);
  }
  if (result.data !== undefined) return result.data;
  const body = (result.error ?? null) as { detail?: unknown; code?: unknown } | null;
  const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${result.response.status}`;
  const code = typeof body?.code === "string" ? body.code : null;
  throw new ApiError(result.response.status, code, detail, result.error ?? null);
}

/** For answers with no body (204 No Content, for example a deletion). */
export async function callEmpty(request: Promise<Result<unknown>>): Promise<void> {
  let result: Result<unknown>;
  try {
    result = await request;
  } catch (e) {
    throw new NetworkError(e instanceof Error ? e.message : undefined);
  }
  if (result.response.ok && result.error === undefined) return;
  const body = (result.error ?? null) as { detail?: unknown; code?: unknown } | null;
  const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${result.response.status}`;
  const code = typeof body?.code === "string" ? body.code : null;
  throw new ApiError(result.response.status, code, detail, result.error ?? null);
}

/** Wording for errors the user can act on. Codes come from the backend (stable). */
const MESSAGES: Record<string, string> = {
  area_single_city_only:
    "Areas in Japan cannot be planned yet (rail travel is not modelled). Choose a city.",
  planning_impossible: "This destination does not have enough places for a plan yet.",
  region_not_available: "This destination's data is not ready yet.",
  destination_not_found: "That destination is no longer in the data. Search again.",
  limit_reached: "You have reached a limit (100 trips, 5 plans per trip). Delete one first.",
  trip_archived: "This is a past trip and can no longer be planned.",
  already_archived: "This trip is already a past trip.",
  not_archived: "Only a past trip has saved places.",
  not_found: "That item no longer exists.",
  recalculation_impossible: "This change does not fit the plan:",
  change_set_stale: "The plan changed after this preview. Preview the change again.",
  change_set_closed: "This preview was already accepted, discarded or replaced.",
  not_recalculable: "Plans made by hand are not recalculated.",
  wrong_place_kind: "Only sights, towns and your own places can be added here.",
  // Dependencies that are down (Phase 9): say which one, and that saved trips still read.
  database_unavailable:
    "The database is paused or unavailable (the free plan pauses it after a week without use). Saved trips can still be read; try again in a few minutes.",
  images_unavailable: "Photos are not available right now. The illustration is shown instead.",
  destination_not_plannable:
    "Suggestions need imported map data, which this destination does not have. Add places yourself.",
  format_too_new: "This file was made by a newer version of Detour. Update the app first.",
  nothing_to_undo: "There is nothing to undo: the plan changed after Optimize.",
  not_enough_stops: "Optimize needs at least three stops with a place.",
  too_many_stops: "This plan has too many stops to optimize at once.",
  stay_overlap: "These days already have a stay. Change the other stay first.",
  day_out_of_range: "Those days are outside the trip.",
};

/** Each reason a plan cannot be made (`planning_impossible` carries them as `issues`). */
export function planningIssues(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [];
  const issues = (error.body as { issues?: { text?: unknown }[] } | null)?.issues;
  return (issues ?? []).flatMap((i) => (typeof i.text === "string" ? [i.text] : []));
}

export function describeError(error: unknown): string {
  if (error instanceof NetworkError) {
    return "The server could not be reached. Check your connection and try again.";
  }
  if (error instanceof ApiError) {
    if (error.code && MESSAGES[error.code]) return MESSAGES[error.code] as string;
    if (error.status === 401)
      return "The server did not accept this installation. Restart the app.";
    if (error.status === 429)
      return "Too many requests from this phone in a short time. Wait a minute and try again.";
    if (error.status >= 500) return "The server had a problem. Try again in a moment.";
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function isOfflineError(error: unknown): boolean {
  return error instanceof NetworkError;
}
