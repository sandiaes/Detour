import type { components } from "@detour/shared";

// What the Regions screen says about the regions the server can import (ADR 033). Pure functions
// over what the backend returns; a figure the backend does not know is not shown.

export type RegionCatalog = components["schemas"]["RegionCatalog"];
export type CatalogRegion = components["schemas"]["CatalogRegion"];
export type ImportJob = components["schemas"]["ImportJob"];
export type RegionRemoval = components["schemas"]["RegionRemoval"];

/** An import that was asked for and has not ended: the screen refreshes while one exists. */
export function importInProgress(region: CatalogRegion): boolean {
  return (
    region.state === "importing" ||
    region.job?.status === "requested" ||
    region.job?.status === "running"
  );
}

export function anyImportInProgress(catalog: RegionCatalog | undefined): boolean {
  return catalog?.regions.some(importInProgress) ?? false;
}

function count(n: number, one: string, many: string): string {
  return `${n.toLocaleString("en")} ${n === 1 ? one : many}`;
}

/** The line under a region's name. */
export function regionLine(region: CatalogRegion): string {
  if (importInProgress(region)) {
    return region.job?.status === "requested" ? "Import requested…" : "Importing…";
  }
  if (region.job?.status === "stalled") return "The import stopped reporting";
  if (region.job?.status === "failed") return "The last import failed";
  switch (region.state) {
    case "available":
      return `Available · ${count(region.places, "place", "places")}`;
    case "disabled":
      return region.places > 0
        ? `Imported, not available · ${count(region.places, "place", "places")}`
        : region.places_kept > 0
          ? `Removed · ${count(region.places_kept, "place", "places")} kept for trips`
          : "Not available";
    default:
      return region.download_mb
        ? `Not imported · about ${region.download_mb} MB to download`
        : "Not imported";
  }
}

/** "Imported data uses 38 MB of 250 MB." */
export function usageLine(catalog: RegionCatalog): string {
  const mb = (bytes: number) => Math.round(bytes / 1_000_000);
  return `Imported data uses ${mb(catalog.geo_bytes)} MB of the ${mb(catalog.geo_limit_bytes)} MB allowed.`;
}

/** What a removal takes away and keeps, for the confirmation. */
export function removalMessage(removal: RegionRemoval): string {
  const mb = Math.max(1, Math.round(removal.bytes_freed_estimate / 1_000_000));
  const n = removal.places_removed;
  const lines = [
    `${n.toLocaleString("en")} ${n === 1 ? "place is" : "places are"} removed, which frees about ${mb} MB.`,
  ];
  if (removal.places_kept > 0) {
    lines.push(
      `${count(removal.places_kept, "place", "places")} your trips use stay, so the trips look the same.`,
    );
  }
  if (removal.trips.length > 0) {
    lines.push(
      `Trips that use this region: ${removal.trips.map((t) => t.title).join(", ")}. Sights near them can no longer be searched.`,
    );
  }
  lines.push("You can import the region again later.");
  return lines.join(" ");
}
