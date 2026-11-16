// Your phones (ADR 034): how a phone and a code read on screen.
import type { components } from "@detour/shared";

import { formatAge, formatDate } from "../util/format";

export type PersonInfo = components["schemas"]["PersonInfo"];
export type DeviceInfo = components["schemas"]["DeviceInfo"];
export type LinkCode = components["schemas"]["LinkCode"];
export type RecoveryCode = components["schemas"]["RecoveryCode"];
export type JoinResult = components["schemas"]["JoinResult"];

/** "This phone", otherwise "Phone 2" by the order the phones were added. */
export function deviceTitle(device: DeviceInfo, index: number): string {
  return device.this_device ? "This phone" : `Phone ${index + 1}`;
}

/** "Added Sat 16 Nov 2026 · last used 5 minutes ago". */
export function deviceDetail(device: DeviceInfo, nowMs: number): string {
  const added = formatDate(device.added_at.slice(0, 10));
  if (device.this_device) return `Added ${added}`;
  return `Added ${added} · last used ${formatAge(Date.parse(device.last_seen_at), nowMs)}`;
}

/** "14:32" in the phone's own time. */
export function clockTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** What a code typed by hand looks like once spaces and hyphens are gone. */
export function codeKind(raw: string): "link" | "recovery" | null {
  const code = raw.replace(/[\s-]/g, "");
  if (code.length === 8) return "link";
  if (code.length === 26) return "recovery";
  return null;
}

export function joinedMessage(result: JoinResult): string {
  const moved =
    result.moved_trips === 0
      ? ""
      : result.moved_trips === 1
        ? " The trip that was on this phone came along."
        : ` The ${result.moved_trips} trips that were on this phone came along.`;
  return `This phone is now one of yours.${moved}`;
}
