import { useState } from "react";

import type { Resource } from "../data/DataProvider";
import { describeError } from "../api/unwrap";
import { formatAge } from "../util/format";
import { Notice } from "./ds";

/**
 * The notices that sit above data already on screen: a saved copy shown offline, a refresh that
 * failed, or the free host waking up. Nothing is shown when the data is current.
 */
export function ResourceNotices({
  resource,
  noun,
  inset = false,
}: {
  resource: Omit<Resource<unknown>, "setData">;
  noun: string;
  /** With the screen gutter, for a parent without padding. */
  inset?: boolean;
}) {
  // The age of a saved copy is worked out once, when the notice first appears.
  const [now] = useState(Date.now);
  if (resource.data === undefined) return null;
  // Offline is told once, by the banner at the top of the app.
  if (resource.offline) return null;
  if (resource.waking && resource.fromCache) {
    return (
      <Notice inset={inset} tone="info" label="Waking the server">
        The free host is starting up, which can take about a minute. Your saved {noun} are shown
        meanwhile.
      </Notice>
    );
  }
  if (resource.error) {
    return (
      <Notice inset={inset} tone="error" action={{ label: "Try again", onPress: resource.refresh }}>
        Could not refresh {noun}. {describeError(resource.error)}
        {resource.savedAt ? ` Showing the copy saved ${formatAge(resource.savedAt, now)}.` : ""}
      </Notice>
    );
  }
  return null;
}
