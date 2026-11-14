"""Command line: ``python -m detour_api.importer {region,gazetteer,images} ...``.

Environment:
  DETOUR_IMPORT_DATABASE_URL   target database (Supabase session pooler, port 5432)
  DETOUR_STAGING_DATABASE_URL  temporary PostGIS used by the region import
  DETOUR_IMPORT_USER_AGENT     overrides the User-Agent sent to the data hosts
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.engine import make_url

from detour_api.importer import pipeline
from detour_api.importer.gazetteer import (
    CITIES_DATASET,
    GEONAMES_BASE,
    read_cities_zip,
    run_gazetteer_import,
)
from detour_api.importer.loader import SourceInfo, import_region
from detour_api.importer.poly import poly_to_wkt
from detour_api.importer.regions import REGIONS, RegionDef
from detour_api.importer.report import dump_json, render_markdown
from detour_api.logging import configure_logging

log = structlog.get_logger("detour.import")


def require_session_mode(url: str) -> None:
    """Supabase's transaction-mode pooler (port 6543) has no session state; refuse it."""
    parsed = make_url(pipeline.libpq_url(url))
    if parsed.port == 6543:
        raise SystemExit(
            "The import needs a session-mode connection: use port 5432 of the Supabase session"
            " pooler, not 6543 (ADR 005)."
        )


def _env(name: str, given: str | None) -> str:
    value = given or os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set (or pass the matching option)")
    return value


def run_region_import(
    region: RegionDef,
    *,
    target_url: str,
    staging_url: str,
    work_dir: Path,
    out_dir: Path | None = None,
    pbf: Path | None = None,
    poly_wkt: str | None = None,
    fetch_poly: bool = True,
    user_agent: str = pipeline.DEFAULT_USER_AGENT,
) -> dict[str, Any]:
    """Download (unless ``pbf`` is given), filter, stage, and load one region."""
    warnings: list[str] = []
    work_dir.mkdir(parents=True, exist_ok=True)
    if pbf is None:
        dl = pipeline.download(region.extract_url, work_dir / "source.osm.pbf", user_agent)
        source_path, url, sha, size = dl.path, dl.url, dl.sha256, dl.size
        if poly_wkt is None and fetch_poly:
            try:
                poly = pipeline.download(region.poly_url, work_dir / "region.poly", user_agent)
                poly_wkt = poly_to_wkt(poly.path.read_text(encoding="utf-8"))
            except (RuntimeError, ValueError) as exc:
                warnings.append(f"Coverage polygon not loaded ({exc}); region geometry unknown.")
    else:
        source_path, url = pbf, None
        sha, size = pipeline.sha256_file(pbf)

    snapshot = pipeline.snapshot_date(source_path)
    filtered = work_dir / "filtered.osm.pbf"
    pipeline.filter_extract(source_path, filtered)
    pipeline.build_staging(staging_url, filtered)

    report, counters = import_region(
        region=region,
        staging_url=staging_url,
        target_url=target_url,
        source=SourceInfo(url=url, sha256=sha, size=size, osm_snapshot_date=snapshot),
        poly_wkt=poly_wkt,
        warnings=warnings,
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(dump_json(report), encoding="utf-8")
        (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
        (out_dir / "review-sample.json").write_text(
            dump_json(counters.review_sample()), encoding="utf-8"
        )
    return report


def _cmd_region(args: argparse.Namespace) -> int:
    region = REGIONS.get(args.region)
    if region is None:
        raise SystemExit(f"unknown region {args.region!r}; known: {', '.join(sorted(REGIONS))}")
    target = _env("DETOUR_IMPORT_DATABASE_URL", args.target_url)
    staging = _env("DETOUR_STAGING_DATABASE_URL", args.staging_url)
    require_session_mode(target)
    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="detour-import-"))
    try:
        report = run_region_import(
            region,
            target_url=target,
            staging_url=staging,
            work_dir=work,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            pbf=Path(args.pbf) if args.pbf else None,
            user_agent=os.environ.get("DETOUR_IMPORT_USER_AGENT", pipeline.DEFAULT_USER_AGENT),
        )
    finally:
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)
    print(render_markdown(report))
    return 0 if report["all_gates_passed"] or args.allow_failed_gates else 3


def _cmd_gazetteer(args: argparse.Namespace) -> int:
    target = _env("DETOUR_IMPORT_DATABASE_URL", args.target_url)
    require_session_mode(target)
    ua = os.environ.get("DETOUR_IMPORT_USER_AGENT", pipeline.DEFAULT_USER_AGENT)
    work = Path(tempfile.mkdtemp(prefix="detour-geonames-"))
    try:
        files: dict[str, Path] = {}
        modified = None
        for name in ("countryInfo.txt", "admin1CodesASCII.txt", "admin2Codes.txt"):
            files[name] = pipeline.download(f"{GEONAMES_BASE}/{name}", work / name, ua).path
        cities = pipeline.download(f"{GEONAMES_BASE}/{args.dataset}.zip", work / "cities.zip", ua)
        modified = cities.last_modified
        counts = run_gazetteer_import(
            target_url=target,
            countries_text=files["countryInfo.txt"].read_text(encoding="utf-8"),
            admin1_text=files["admin1CodesASCII.txt"].read_text(encoding="utf-8"),
            admin2_text=files["admin2Codes.txt"].read_text(encoding="utf-8"),
            city_lines=read_cities_zip(cities.path, args.dataset),
            country_codes=sorted(set(args.countries)),
            geonames_date=modified,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


def _cmd_images(args: argparse.Namespace) -> int:
    """Resolve photos for a region's attractions and its countries' cities (ADR 022)."""
    from detour_api.adapters.wikimedia import WikimediaClient
    from detour_api.db import make_engine
    from detour_api.images import resolver
    from detour_api.images.store import MemoryImageStore, make_store
    from detour_api.settings import Settings, normalize_database_url

    region = REGIONS.get(args.region)
    if region is None:
        raise SystemExit(f"unknown region {args.region!r}; known: {', '.join(sorted(REGIONS))}")
    target = _env("DETOUR_IMPORT_DATABASE_URL", args.target_url)
    require_session_mode(target)
    settings = Settings()
    store = make_store(settings)
    if store is None:
        if not args.dry_run_storage:
            raise SystemExit(
                "DETOUR_SUPABASE_URL and DETOUR_SUPABASE_SERVICE_KEY are not set (Storage);"
                " pass --dry-run-storage to resolve without keeping the files"
            )
        store = MemoryImageStore()
    engine = make_engine(normalize_database_url(target))
    try:
        client = WikimediaClient(settings, engine)
        if not client.enabled:
            raise SystemExit("the Wikimedia adapter is disabled (DETOUR_WIKIMEDIA_ENABLED)")
        reports: dict[str, object] = {}
        if args.cities:
            cands = resolver.city_candidates(engine, region.countries, args.cities)
            reports["cities"] = resolver.resolve(engine, client, store, settings, cands).as_dict()
        if args.places:
            cands = resolver.place_candidates(engine, region.id, args.places)
            reports["places"] = resolver.resolve(engine, client, store, settings, cands).as_dict()
        with engine.begin() as conn:
            from sqlalchemy import text

            reports["stored"] = dict(
                conn.execute(
                    text(
                        "SELECT count(*) AS images, coalesce(sum(bytes), 0) AS bytes FROM geo.image"
                    )
                )
                .mappings()
                .one()
            )
    finally:
        engine.dispose()
    out = json.dumps(reports, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


def _cmd_countries(args: argparse.Namespace) -> int:
    region = REGIONS.get(args.region)
    if region is None:
        raise SystemExit(f"unknown region {args.region!r}; known: {', '.join(sorted(REGIONS))}")
    print(" ".join(region.countries))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging("INFO")
    parser = argparse.ArgumentParser(prog="python -m detour_api.importer")
    sub = parser.add_subparsers(dest="command", required=True)

    region = sub.add_parser("region", help="import one region's OpenStreetMap extract")
    region.add_argument("region", help=f"one of: {', '.join(sorted(REGIONS))}")
    region.add_argument("--pbf", help="use this local file instead of downloading")
    region.add_argument("--target-url")
    region.add_argument("--staging-url")
    region.add_argument("--work-dir")
    region.add_argument("--out-dir", help="write report.json, report.md and review-sample.json")
    region.add_argument("--keep-work", action="store_true")
    region.add_argument(
        "--allow-failed-gates",
        action="store_true",
        help="exit 0 even if a readiness gate fails (the region then stays disabled)",
    )
    region.set_defaults(func=_cmd_region)

    gaz = sub.add_parser("gazetteer", help="import GeoNames countries, currencies and cities")
    gaz.add_argument("countries", nargs="+", help="ISO 3166-1 alpha-2 codes, for example AT CZ")
    gaz.add_argument("--dataset", default=CITIES_DATASET)
    gaz.add_argument("--target-url")
    gaz.set_defaults(func=_cmd_gazetteer)

    images = sub.add_parser("images", help="find, resize and store photos (ADR 022)")
    images.add_argument("region", help=f"one of: {', '.join(sorted(REGIONS))}")
    images.add_argument("--places", type=int, default=500, help="attractions to look up (0: none)")
    images.add_argument("--cities", type=int, default=100, help="cities to look up (0: none)")
    images.add_argument("--target-url")
    images.add_argument("--out", help="write the report as JSON to this file")
    images.add_argument(
        "--dry-run-storage",
        action="store_true",
        help="keep the files in memory only: measures coverage without Supabase Storage",
    )
    images.set_defaults(func=_cmd_images)

    countries = sub.add_parser("countries", help="print the country codes of a region")
    countries.add_argument("region")
    countries.set_defaults(func=_cmd_countries)

    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
