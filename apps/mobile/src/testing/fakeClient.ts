import type { ApiClient } from "@detour/shared";

// A stand-in for the typed client. Handlers are keyed "METHOD /v1/path/{template}" and return the
// body (a 200), `{ status, body }` for another status, or throw a TypeError to act as "offline".

export type FakeHandler = (call: {
  path: string;
  params: Record<string, unknown>;
  body: unknown;
}) => unknown | Promise<unknown>;

export type FakeCall = {
  method: string;
  path: string;
  params: Record<string, unknown>;
  body: unknown;
};

export type FakeClient = ApiClient & { calls: FakeCall[]; count: (key: string) => number };

export function createFakeClient(handlers: Record<string, FakeHandler>): FakeClient {
  const calls: FakeCall[] = [];
  const make =
    (method: string) =>
    async (path: string, init?: { params?: Record<string, unknown>; body?: unknown }) => {
      const params = {
        ...((init?.params?.path as Record<string, unknown> | undefined) ?? {}),
        ...((init?.params?.query as Record<string, unknown> | undefined) ?? {}),
      };
      calls.push({ method, path, params, body: init?.body });
      const handler = handlers[`${method} ${path}`];
      if (!handler) throw new Error(`FakeClient: no handler for ${method} ${path}`);
      const result = await handler({ path, params, body: init?.body });
      if (result && typeof result === "object" && "status" in result && "body" in result) {
        const { status, body } = result as { status: number; body: unknown };
        return {
          error: JSON.parse(JSON.stringify(body)),
          response: new Response(null, { status }),
        };
      }
      // A real response is parsed afresh each time; never hand out the test's own objects.
      const data = result === undefined ? result : JSON.parse(JSON.stringify(result));
      return { data, response: new Response(null, { status: 200 }) };
    };
  const client = {
    GET: make("GET"),
    POST: make("POST"),
    PATCH: make("PATCH"),
    PUT: make("PUT"),
    DELETE: make("DELETE"),
    calls,
    count: (key: string) => calls.filter((c) => `${c.method} ${c.path}` === key).length,
  };
  return client as unknown as FakeClient;
}

export const offline = (): never => {
  throw new TypeError("Network request failed");
};
