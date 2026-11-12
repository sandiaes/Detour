import { useEffect, useState } from "react";

/**
 * How many of `total` things to show now. It starts with one batch and adds a batch every
 * `intervalMs`, so a day with many stops draws a few markers at a time instead of freezing the
 * map while all of them are created (performance requirement: markers load progressively).
 * Starts again whenever `resetKey` or `total` changes.
 */
export function useProgressiveCount(
  total: number,
  resetKey: string,
  { batch = 6, intervalMs = 60 }: { batch?: number; intervalMs?: number } = {},
): number {
  const runKey = `${resetKey}:${total}`;
  const [progress, setProgress] = useState({ runKey, count: Math.min(total, batch) });

  useEffect(() => {
    if (total <= batch) return;
    const id = setInterval(() => {
      setProgress((p) => {
        const base = p.runKey === runKey ? p.count : Math.min(total, batch);
        const count = Math.min(total, base + batch);
        if (count >= total) clearInterval(id);
        return { runKey, count };
      });
    }, intervalMs);
    return () => clearInterval(id);
  }, [runKey, total, batch, intervalMs]);

  // A new run has not ticked yet: show its first batch rather than the old run's count.
  const count = progress.runKey === runKey ? progress.count : Math.min(total, batch);
  return Math.min(count, total);
}
