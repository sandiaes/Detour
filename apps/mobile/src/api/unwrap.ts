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

/** Wording for errors the user can act on. Codes come from the backend (stable). */
const MESSAGES: Record<string, string> = {
  area_not_supported: "Planning for whole areas is not available yet. Choose a city.",
  planning_impossible: "This destination does not have enough places for a plan yet.",
  region_not_available: "This destination's data is not ready yet.",
  destination_not_found: "That destination is no longer in the data. Search again.",
  unknown_currency: "That currency code is not known. Use a three-letter code such as EUR.",
  limit_reached: "You have reached a limit (100 trips, 5 plans per trip). Delete one first.",
  trip_archived: "This is a past trip and can no longer be planned.",
  not_found: "That item no longer exists.",
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
    if (error.status >= 500) return "The server had a problem. Try again in a moment.";
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function isOfflineError(error: unknown): boolean {
  return error instanceof NetworkError;
}
