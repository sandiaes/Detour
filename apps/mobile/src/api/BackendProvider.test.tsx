import { act, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import {
  BackendProvider,
  RETRY_MAX_MS,
  describeConnectionError,
  retryDelayMs,
  useBackend,
} from "./BackendProvider";
import { ConnectionError, connect } from "./connect";

jest.mock("./connect", () => {
  const actual = jest.requireActual("./connect");
  return { ...actual, connect: jest.fn() };
});
jest.mock("./tokenStore", () => ({ secureTokenStore: { get: jest.fn(), set: jest.fn() } }));

const connectMock = connect as jest.MockedFunction<typeof connect>;

function Phase() {
  const { state } = useBackend();
  return <Text testID="phase">{state.phase}</Text>;
}

beforeEach(() => {
  jest.useFakeTimers();
  connectMock.mockReset();
});
afterEach(() => jest.useRealTimers());

test("the wait doubles from 5 seconds and stops at a minute", () => {
  expect([1, 2, 3, 4, 5, 6, 20].map(retryDelayMs)).toEqual([
    5_000,
    10_000,
    20_000,
    40_000,
    RETRY_MAX_MS,
    RETRY_MAX_MS,
    RETRY_MAX_MS,
  ]);
});

test("after a failed connection it tries again by itself, with a longer wait each time", async () => {
  connectMock
    .mockRejectedValueOnce(new TypeError("Network request failed"))
    .mockRejectedValueOnce(new TypeError("Network request failed"))
    .mockResolvedValueOnce({} as never);
  await render(
    <BackendProvider>
      <Phase />
    </BackendProvider>,
  );
  expect(screen.getByTestId("phase")).toHaveTextContent("error");
  expect(connectMock).toHaveBeenCalledTimes(1);

  await act(async () => jest.advanceTimersByTime(4_999));
  expect(connectMock).toHaveBeenCalledTimes(1);
  await act(async () => jest.advanceTimersByTime(1));
  expect(connectMock).toHaveBeenCalledTimes(2);
  expect(screen.getByTestId("phase")).toHaveTextContent("error");

  // The second wait is 10 seconds.
  await act(async () => jest.advanceTimersByTime(9_999));
  expect(connectMock).toHaveBeenCalledTimes(2);
  await act(async () => jest.advanceTimersByTime(1));
  expect(connectMock).toHaveBeenCalledTimes(3);
  expect(screen.getByTestId("phase")).toHaveTextContent("ready");
});

test("a build without a backend address does not keep trying", async () => {
  connectMock.mockRejectedValue(new ConnectionError("no URL", { permanent: true }));
  await render(
    <BackendProvider>
      <Phase />
    </BackendProvider>,
  );
  await act(async () => jest.advanceTimersByTime(10 * RETRY_MAX_MS));
  expect(connectMock).toHaveBeenCalledTimes(1);
});

test("the banner's reason is in plain words, never a stack or an address", () => {
  const abort = new Error("aborted");
  abort.name = "AbortError";
  expect(describeConnectionError(abort)).toMatch(/did not answer in time/);
  expect(describeConnectionError(new TypeError("Network request failed"))).toMatch(
    /internet connection/,
  );
  expect(describeConnectionError(new ConnectionError("Config request failed (HTTP 502)."))).toBe(
    "Config request failed (HTTP 502).",
  );
});
