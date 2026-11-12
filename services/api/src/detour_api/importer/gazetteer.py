"""GeoNames gazetteer import: countries, currencies, admin-code names and cities.

Source: the GeoNames dump files ``countryInfo.txt``, ``admin1CodesASCII.txt``,
``admin2Codes.txt`` and ``cities1000.zip`` (licence CC BY 4.0, credit GeoNames).

**File layouts were not verified against the dump's readme** (the host is not reachable from the
development environment; docs/decisions/012). Defences: ``countryInfo.txt`` columns are looked up
by the names in the file's own header line; the other files must have exactly the column count
below or the import stops with the line number; nothing is guessed.
"""

import io
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import structlog

from detour_api.importer.loader import assign_cities, check_target
from detour_api.importer.pipeline import libpq_url
from detour_api.textnorm import normalize_text

log = structlog.get_logger("detour.import")

GEONAMES_BASE = "https://download.geonames.org/export/dump"
CITIES_DATASET = "cities1000"  # all places with more than 1,000 inhabitants
ALT_NAMES_CAP = 40
GEONAME_COLUMNS = 19
CODE_FILE_COLUMNS = 4


class GazetteerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CountryRow:
    iso2: str
    iso3: str
    name: str
    currency_code: str | None
    currency_name: str | None


def parse_country_info(text: str) -> list[CountryRow]:
    header: list[str] | None = None
    rows: list[CountryRow] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if line.startswith("#ISO"):
                header = line.lstrip("#").split("\t")
            continue
        if not line.strip():
            continue
        if header is None:
            raise GazetteerError("countryInfo.txt has no '#ISO ...' header line")
        needed = ("ISO", "ISO3", "Country", "CurrencyCode", "CurrencyName")
        missing = [h for h in needed if h not in header]
        if missing:
            raise GazetteerError(f"countryInfo.txt header lacks columns: {missing}")
        cells = line.split("\t")
        if len(cells) < len(header):
            raise GazetteerError(f"countryInfo.txt: short row for {cells[:1]}")
        by_name = dict(zip(header, cells, strict=False))
        code = by_name["CurrencyCode"].strip()
        rows.append(
            CountryRow(
                iso2=by_name["ISO"].strip(),
                iso3=by_name["ISO3"].strip(),
                name=by_name["Country"].strip(),
                currency_code=code or None,
                currency_name=by_name["CurrencyName"].strip() or None,
            )
        )
    if not rows:
        raise GazetteerError("countryInfo.txt contains no countries")
    return rows


def parse_code_file(text: str, countries: set[str]) -> Iterator[tuple[str, str, str, int | None]]:
    """``admin1CodesASCII.txt`` / ``admin2Codes.txt``: code, name, ascii name, geoname id."""
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) != CODE_FILE_COLUMNS:
            raise GazetteerError(f"admin code file line {number}: {len(cells)} columns")
        code, name, ascii_name, geoname_id = cells
        if code.split(".", 1)[0] in countries:
            yield code, name, ascii_name, int(geoname_id) if geoname_id.isdigit() else None


@dataclass(frozen=True)
class CityRow:
    id: int
    name: str
    ascii_name: str
    name_norm: str
    alt_names: list[str] | None
    alt_names_norm: str | None
    country_iso2: str
    admin1_code: str | None
    admin2_code: str | None
    population: int | None
    timezone: str | None
    feature_code: str | None
    lon: float
    lat: float


def pick_alt_names(name: str, raw: str) -> list[str] | None:
    """Distinct alternate names (by normalised form), shortest first, at most ``ALT_NAMES_CAP``."""
    seen = {normalize_text(name)}
    kept: list[tuple[int, str, str]] = []
    for alt in raw.split(","):
        alt = alt.strip()
        norm = normalize_text(alt)
        if not alt or not norm or norm in seen:
            continue
        seen.add(norm)
        kept.append((len(norm), norm, alt))
    kept.sort()
    return [alt for _, _, alt in kept[:ALT_NAMES_CAP]] or None


def parse_cities(lines: Iterable[str], countries: set[str]) -> Iterator[CityRow]:
    for number, line in enumerate(lines, start=1):
        line = line.rstrip("\n")
        if not line:
            continue
        cells = line.split("\t")
        if len(cells) != GEONAME_COLUMNS:
            raise GazetteerError(f"cities file line {number}: {len(cells)} columns, expected 19")
        country = cells[8]
        if country not in countries:
            continue
        alt = pick_alt_names(cells[1], cells[3])
        population = int(cells[14]) if cells[14].isdigit() else 0
        yield CityRow(
            id=int(cells[0]),
            name=cells[1],
            ascii_name=cells[2],
            name_norm=normalize_text(cells[1]),
            alt_names=alt,
            alt_names_norm="|".join(normalize_text(a) for a in alt) if alt else None,
            country_iso2=country,
            admin1_code=cells[10] or None,
            admin2_code=cells[11] or None,
            population=population or None,  # GeoNames writes 0 when the population is unknown
            timezone=cells[17] or None,
            feature_code=cells[7] or None,
            lon=float(cells[5]),
            lat=float(cells[4]),
        )


def read_cities_zip(path: Path, dataset: str = CITIES_DATASET) -> Iterator[str]:
    with zipfile.ZipFile(path) as archive:
        member = f"{dataset}.txt"
        if member not in archive.namelist():
            raise GazetteerError(f"{path.name} has no {member}")
        with archive.open(member) as raw:
            yield from io.TextIOWrapper(raw, encoding="utf-8")


def load_gazetteer(
    conn: psycopg.Connection[Any],
    *,
    countries_text: str,
    admin1_text: str,
    admin2_text: str,
    city_lines: Iterable[str],
    country_codes: list[str],
    geonames_date: date | None,
) -> dict[str, int]:
    """Load countries (all), currencies (all), and codes and cities of ``country_codes``."""
    wanted = set(country_codes)
    country_rows = parse_country_info(countries_text)
    known = {c.iso2 for c in country_rows}
    unknown = wanted - known
    if unknown:
        raise GazetteerError(f"not in countryInfo.txt: {sorted(unknown)}")

    currencies: dict[str, str] = {}
    for c in country_rows:
        if c.currency_code and c.currency_name:
            previous = currencies.get(c.currency_code)
            currencies[c.currency_code] = (
                min(c.currency_name, previous) if previous else c.currency_name
            )

    counts: dict[str, int] = {}
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(7240001)")
        for code, cname in sorted(currencies.items()):
            conn.execute(
                "INSERT INTO geo.currency (code, name) VALUES (%s, %s)"
                " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name",
                (code, cname),
            )
        counts["currencies"] = len(currencies)
        for c in sorted(country_rows, key=lambda r: r.iso2):
            conn.execute(
                "INSERT INTO geo.country (iso2, iso3, name, default_currency_code)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (iso2) DO UPDATE SET iso3 = EXCLUDED.iso3, name = EXCLUDED.name,"
                " default_currency_code = EXCLUDED.default_currency_code",
                (
                    c.iso2,
                    c.iso3,
                    c.name,
                    c.currency_code if c.currency_code in currencies else None,
                ),
            )
        counts["countries"] = len(country_rows)

        n_codes = 0
        for level, text in ((1, admin1_text), (2, admin2_text)):
            for code, name, ascii_name, gid in parse_code_file(text, wanted):
                conn.execute(
                    "INSERT INTO geo.admin_code (code, level, country_iso2, name, ascii_name,"
                    " geoname_id) VALUES (%s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (code) DO UPDATE SET level = EXCLUDED.level,"
                    " name = EXCLUDED.name, ascii_name = EXCLUDED.ascii_name,"
                    " geoname_id = EXCLUDED.geoname_id",
                    (code, level, code.split(".", 1)[0], name, ascii_name, gid),
                )
                n_codes += 1
        counts["admin_codes"] = n_codes

        conn.execute(
            "CREATE TEMP TABLE stage_city (LIKE geo.city INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        n_cities = 0
        with (
            conn.cursor() as cur,
            cur.copy(
                "COPY stage_city (id, name, ascii_name, name_norm, alt_names, alt_names_norm,"
                " country_iso2, admin1_code, admin2_code, population, timezone, feature_code, geom,"
                " geonames_date) FROM STDIN"
            ) as copy,
        ):
            for city in parse_cities(city_lines, wanted):
                copy.write_row(
                    (
                        city.id,
                        city.name,
                        city.ascii_name,
                        city.name_norm,
                        city.alt_names,
                        city.alt_names_norm,
                        city.country_iso2,
                        city.admin1_code,
                        city.admin2_code,
                        city.population,
                        city.timezone,
                        city.feature_code,
                        f"SRID=4326;POINT({city.lon!r} {city.lat!r})",
                        geonames_date,
                    )
                )
                n_cities += 1
        conn.execute(
            """
            INSERT INTO geo.city (id, name, ascii_name, name_norm, alt_names, alt_names_norm,
                country_iso2, admin1_code, admin2_code, population, timezone, feature_code, geom,
                geonames_date)
            SELECT id, name, ascii_name, name_norm, alt_names, alt_names_norm, country_iso2,
                admin1_code, admin2_code, population, timezone, feature_code, geom, geonames_date
            FROM stage_city
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, ascii_name = EXCLUDED.ascii_name,
                name_norm = EXCLUDED.name_norm, alt_names = EXCLUDED.alt_names,
                alt_names_norm = EXCLUDED.alt_names_norm, country_iso2 = EXCLUDED.country_iso2,
                admin1_code = EXCLUDED.admin1_code, admin2_code = EXCLUDED.admin2_code,
                population = EXCLUDED.population, timezone = EXCLUDED.timezone,
                feature_code = EXCLUDED.feature_code, geom = EXCLUDED.geom,
                geonames_date = EXCLUDED.geonames_date
            """
        )
        removed = conn.execute(
            "DELETE FROM geo.city c WHERE c.country_iso2 = ANY (%s)"
            " AND NOT EXISTS (SELECT 1 FROM stage_city s WHERE s.id = c.id)",
            (country_codes,),
        ).rowcount
        counts["cities"] = n_cities
        counts["cities_removed"] = removed

        # Single-country regions: their administrative areas belong to that country.
        conn.execute(
            "UPDATE geo.admin_area a SET country_iso2 = r.country_codes[1]"
            " FROM geo.region r WHERE a.region_id = r.id AND a.country_iso2 IS NULL"
            " AND cardinality(r.country_codes) = 1"
            " AND EXISTS (SELECT 1 FROM geo.country c WHERE c.iso2 = r.country_codes[1])"
        )
        assigned = 0
        for (region_id,) in conn.execute(
            "SELECT id FROM geo.region WHERE country_codes && %s ORDER BY id", (country_codes,)
        ).fetchall():
            assigned += assign_cities(conn, region_id)
        counts["places_city_assigned"] = assigned
    conn.execute("ANALYZE geo.city")
    return counts


def run_gazetteer_import(
    *,
    target_url: str,
    countries_text: str,
    admin1_text: str,
    admin2_text: str,
    city_lines: Iterable[str],
    country_codes: list[str],
    geonames_date: date | None,
) -> dict[str, int]:
    with psycopg.connect(libpq_url(target_url)) as conn:
        check_target(conn)
        counts = load_gazetteer(
            conn,
            countries_text=countries_text,
            admin1_text=admin1_text,
            admin2_text=admin2_text,
            city_lines=city_lines,
            country_codes=country_codes,
            geonames_date=geonames_date,
        )
    log.info("gazetteer_done", **counts)
    return counts
