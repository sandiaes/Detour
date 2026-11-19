import {
  type CatalogRegion,
  type RegionCatalog,
  anyImportInProgress,
  groupByContinent,
  groupSummary,
  hasData,
  megabytes,
  regionLine,
  removalMessage,
  usageLine,
} from "./regions";

function region(over: Partial<CatalogRegion> = {}): CatalogRegion {
  return {
    id: "greater-london",
    name: "Greater London",
    continent: "Europe",
    country_codes: ["GB"],
    state: "not_imported",
    places: 0,
    places_kept: 0,
    bytes: null,
    job: null,
    ...over,
  };
}

const job = (status: string, message: string | null = null) =>
  ({
    id: "j1",
    status,
    message,
    run_url: null,
    requested_at: "2027-01-01T10:00:00Z",
    updated_at: "2027-01-01T10:00:00Z",
  }) as never;

describe("regionLine", () => {
  test("a region that was never imported just says so: no size is guessed", () => {
    expect(regionLine(region())).toBe("Not imported");
  });
  test("sizes are in megabytes, or gigabytes from 1,000", () => {
    expect(megabytes(38)).toBe("38 MB");
    expect(megabytes(2100)).toBe("2.1 GB");
    expect(megabytes(2000)).toBe("2 GB");
    expect(megabytes(0.2)).toBe("1 MB");
  });
  test("an imported region says how much room it takes, when known", () => {
    expect(regionLine(region({ state: "available", places: 3, bytes: 12_400_000 }))).toBe(
      "Available · 3 places · about 12 MB",
    );
    expect(regionLine(region({ state: "disabled", places_kept: 2, bytes: 90_000 }))).toBe(
      "Removed · 2 places kept for trips · about 1 MB",
    );
  });
  test("an available region counts its places", () => {
    expect(regionLine(region({ state: "available", places: 1 }))).toBe("Available · 1 place");
    expect(regionLine(region({ state: "available", places: 12345 }))).toBe(
      "Available · 12,345 places",
    );
  });
  test("a removed region says trips kept their places", () => {
    expect(regionLine(region({ state: "disabled", places_kept: 3 }))).toBe(
      "Removed · 3 places kept for trips",
    );
  });
  test("an import in progress, stalled or failed is said first", () => {
    expect(regionLine(region({ job: job("requested") }))).toBe("Import requested…");
    expect(regionLine(region({ job: job("running") }))).toBe("Importing…");
    expect(regionLine(region({ state: "importing" }))).toBe("Importing…");
    expect(regionLine(region({ job: job("stalled") }))).toBe("The import stopped reporting");
    expect(regionLine(region({ job: job("failed") }))).toBe("The last import failed");
    expect(regionLine(region({ state: "available", places: 5, job: job("succeeded") }))).toBe(
      "Available · 5 places",
    );
  });
});

test("the screen watches while any import is under way", () => {
  const catalog = (regions: CatalogRegion[]): RegionCatalog =>
    ({
      can_manage: true,
      import_enabled: true,
      geo_bytes: 0,
      geo_limit_bytes: 1,
      regions,
    }) as never;
  expect(anyImportInProgress(undefined)).toBe(false);
  expect(anyImportInProgress(catalog([region()]))).toBe(false);
  expect(anyImportInProgress(catalog([region(), region({ job: job("running") })]))).toBe(true);
  expect(anyImportInProgress(catalog([region({ job: job("stalled") })]))).toBe(false);
});

test("the usage line rounds to megabytes", () => {
  expect(usageLine({ geo_bytes: 38_400_000, geo_limit_bytes: 250_000_000 } as never)).toBe(
    "Imported data uses 38 MB of the 250 MB allowed.",
  );
});

test("the removal message says what goes, what stays and which trips use it", () => {
  const text = removalMessage({
    region_id: "austria",
    name: "Austria",
    places_total: 100,
    places_removed: 99,
    places_kept: 1,
    admin_areas_removed: 2,
    admin_areas_kept: 0,
    cities_removed: 40,
    cities_kept: 1,
    trips: [{ id: "t", title: "Graz", status: "past" }],
    bytes_freed_estimate: 5_400_000,
  });
  expect(text).toContain("99 places are removed, which frees about 5 MB.");
  expect(text).toContain("1 place your trips use stay");
  expect(text).toContain("40 cities of its countries are removed");
  expect(text).toContain("Graz");
  expect(text).toContain("import the region again");
});

test("regions are grouped under their continent in the order sent", () => {
  const groups = groupByContinent([
    region({ id: "japan", name: "Japan", continent: "Asia" }),
    region({ id: "austria", name: "Austria", continent: "Europe" }),
    region({ id: "spain", name: "Spain", continent: "Europe" }),
    region({ id: "new-york", name: "New York State", continent: "North America" }),
  ]);
  expect(groups.map((g) => g.continent)).toEqual(["Asia", "Europe", "North America"]);
  expect(groups[1]?.regions.map((r) => r.name)).toEqual(["Austria", "Spain"]);
  expect(groupByContinent([])).toEqual([]);
});

test("a region has data when it is available, has places or has an import under way", () => {
  expect(hasData(region())).toBe(false);
  expect(hasData(region({ state: "available", places: 2 }))).toBe(true);
  expect(hasData(region({ state: "disabled", places: 5 }))).toBe(true);
  expect(hasData(region({ state: "disabled", places_kept: 3 }))).toBe(false);
  expect(hasData(region({ job: job("running") }))).toBe(true);
});

test("a group says how many regions it has and how many are imported", () => {
  expect(groupSummary([region()])).toBe("1 region");
  expect(groupSummary([region(), region()])).toBe("2 regions");
  expect(groupSummary([region({ state: "available", places: 1 }), region()])).toBe(
    "1 imported · 2 regions",
  );
});
