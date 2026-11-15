import { render, screen } from "@testing-library/react-native";

import { ApiError, NetworkError, describeError } from "../api/unwrap";
import { ResourceNotices } from "./ResourceNotices";

const base = {
  status: "ready" as const,
  data: [] as unknown,
  fromCache: true,
  offline: false,
  refreshing: false,
  error: null as unknown,
  waking: false,
  refresh: () => {},
};

test("a paused database keeps the saved copy on screen and says how old it is", async () => {
  const savedAt = Date.now() - 3 * 3_600_000;
  await render(
    <ResourceNotices
      noun="trips"
      resource={{
        ...base,
        savedAt,
        error: new ApiError(503, "database_unavailable", "the database is unavailable"),
      }}
    />,
  );
  expect(screen.getByText(/The database is paused or unavailable/)).toBeOnTheScreen();
  expect(screen.getByText(/Showing the copy saved 3 hours ago/)).toBeOnTheScreen();
});

test("offline, the saved copy is labelled with its age", async () => {
  const savedAt = Date.now() - 2 * 86_400_000;
  await render(
    <ResourceNotices
      noun="trips"
      resource={{ ...base, savedAt, offline: true, error: new NetworkError() }}
    />,
  );
  expect(screen.getByText(/Showing trips saved 2 days ago/)).toBeOnTheScreen();
});

test("each dependency that is down has its own plain message", () => {
  expect(describeError(new ApiError(503, "images_unavailable", "x"))).toMatch(/illustration/);
  expect(describeError(new ApiError(429, null, "x"))).toMatch(/Too many requests/);
  expect(describeError(new NetworkError())).toMatch(/could not be reached/);
});
