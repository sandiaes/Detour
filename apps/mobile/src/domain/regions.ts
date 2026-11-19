import type { components } from "@detour/shared";

// What the Regions screen says about the regions the server can import (ADR 033). Pure functions
// over what the backend returns; a figure the backend does not know is not shown.

export type RegionCatalog = components["schemas"]["RegionCatalog"];
export type CatalogRegion = components["schemas"]["CatalogRegion"];
export type ImportJob = components["schemas"]["ImportJob"];
export type RegionRemoval = components["schemas"]["RegionRemoval"];

/** The regions under their continent headings, in the order the server sent them (it sorts by
 * continent, then imported first, then by name). */
export function groupByContinent(
  regions: CatalogRegion[],
): { continent: string; regions: CatalogRegion[] }[] {
  const groups: { continent: string; regions: CatalogRegion[] }[] = [];
  for (const region of regions) {
    const last = groups[groups.length - 1];
    if (last && last.continent === region.continent) last.regions.push(region);
    else groups.push({ continent: region.continent, regions: [region] });
  }
  return groups;
}

/** True when the region holds data or has an import under way: it is worth showing open. */
export function hasData(region: CatalogRegion): boolean {
  return region.state === "available" || region.places > 0 || importInProgress(region);
}

/** "3 imported · 24 regions", or just "24 regions" when none is imported. */
export function groupSummary(regions: CatalogRegion[]): string {
  const total = `${regions.length} ${regions.length === 1 ? "region" : "regions"}`;
  const imported = regions.filter(hasData).length;
  return imported > 0 ? `${imported} imported · ${total}` : total;
}

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

/** A size in megabytes, or gigabytes from 1,000: "38 MB", "2.1 GB". */
export function megabytes(mb: number): string {
  if (mb >= 1000) return `${(mb / 1000).toFixed(1).replace(/\.0$/, "")} GB`;
  return `${Math.max(1, Math.round(mb))} MB`;
}

function count(n: number, one: string, many: string): string {
  return `${n.toLocaleString("en")} ${n === 1 ? one : many}`;
}

/** " · about 12 MB" when the server knows roughly how much room the region takes. */
function sizeSuffix(region: CatalogRegion): string {
  return region.bytes ? ` · about ${megabytes(region.bytes / 1_000_000)}` : "";
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
      return `Available · ${count(region.places, "place", "places")}${sizeSuffix(region)}`;
    case "disabled":
      return region.places > 0
        ? `Imported, not available · ${count(region.places, "place", "places")}${sizeSuffix(region)}`
        : region.places_kept > 0
          ? `Removed · ${count(region.places_kept, "place", "places")} kept for trips${sizeSuffix(region)}`
          : "Not available";
    default:
      return "Not imported";
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
  if (removal.cities_removed > 0) {
    lines.push(
      `${count(removal.cities_removed, "city", "cities")} of its countries are removed with them and load again with the next import.`,
    );
  }
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
