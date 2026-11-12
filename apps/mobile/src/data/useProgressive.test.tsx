import { act, renderHook } from "@testing-library/react-native";

import { useProgressiveCount } from "./useProgressive";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test("starts with one batch and adds one per interval until all are shown", async () => {
  const { result } = await renderHook(() =>
    useProgressiveCount(20, "a", { batch: 8, intervalMs: 50 }),
  );
  expect(result.current).toBe(8);
  await act(async () => void jest.advanceTimersByTime(50));
  expect(result.current).toBe(16);
  await act(async () => void jest.advanceTimersByTime(50));
  expect(result.current).toBe(20);
  await act(async () => void jest.advanceTimersByTime(500));
  expect(result.current).toBe(20);
});

test("starts again when the key changes, and never exceeds the total", async () => {
  const { result, rerender } = await renderHook(
    ({ total, key }: { total: number; key: string }) =>
      useProgressiveCount(total, key, { batch: 5 }),
    { initialProps: { total: 12, key: "a" } },
  );
  await act(async () => void jest.advanceTimersByTime(1000));
  expect(result.current).toBe(12);
  await rerender({ total: 3, key: "b" });
  expect(result.current).toBe(3);
});
