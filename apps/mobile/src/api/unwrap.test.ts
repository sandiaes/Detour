import {
  ApiError,
  NetworkError,
  call,
  describeError,
  isOfflineError,
  planningIssues,
} from "./unwrap";

const res = (status: number) => new Response(null, { status });

test("returns the data of a successful call", async () => {
  await expect(call(Promise.resolve({ data: { a: 1 }, response: res(200) }))).resolves.toEqual({
    a: 1,
  });
});

test("a rejected request is a network error", async () => {
  const e: unknown = await call(Promise.reject(new TypeError("Network request failed"))).catch(
    (x: unknown) => x,
  );
  expect(e).toBeInstanceOf(NetworkError);
  expect(isOfflineError(e)).toBe(true);
});

test("an error body becomes an ApiError with the stable code", async () => {
  const e: unknown = await call(
    Promise.resolve({
      error: { detail: "nope", code: "area_single_city_only" },
      response: res(422),
    }),
  ).catch((x: unknown) => x);
  expect(e).toBeInstanceOf(ApiError);
  expect((e as ApiError).status).toBe(422);
  expect((e as ApiError).code).toBe("area_single_city_only");
  expect(describeError(e)).toMatch(/Choose a city/);
});

test("messages for network, server and unknown problems", () => {
  expect(describeError(new NetworkError())).toMatch(/could not be reached/);
  expect(describeError(new ApiError(503, null, "x"))).toMatch(/server had a problem/);
  expect(describeError(new ApiError(418, "teapot", "I am a teapot"))).toBe("I am a teapot");
  expect(describeError(new Error("plain"))).toBe("plain");
});

test("planning issues are read from the error body", () => {
  const e = new ApiError(422, "planning_impossible", "x", {
    issues: [{ code: "A", text: "Too few places." }],
  });
  expect(planningIssues(e)).toEqual(["Too few places."]);
  expect(planningIssues(new Error("x"))).toEqual([]);
});
