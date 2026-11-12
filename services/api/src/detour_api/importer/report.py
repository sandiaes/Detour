"""Data quality report and the region readiness gates of ADR 009.

Everything is computed from counters filled while the import streams the data, then cross-checked
against the database before the transaction commits (see ``loader.py``). Percentages with an
empty denominator are ``None`` (unknown) and a gate on an unknown value does not pass.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from hashlib import md5
from typing import Any

from detour_api.importer.derive import PlaceRow
from detour_api.importer.selection import REVIEW_CLASSES, Decision
from detour_api.textnorm import has_latin_letters

# ADR 009, gate 6: half of Supabase Free's 500 MB (decimal megabytes, as in spike S2).
GEO_SIZE_LIMIT_BYTES = 250 * 1_000_000
# ADR 009, gate 5 allows a display rule instead of the Latin-letter share. None is implemented in
# Phase 2, so the share decides. Set to True only when a display rule exists.
DISPLAY_RULE_IMPLEMENTED = False

MIN_RESTAURANT_NAMED_PCT = 90.0
MIN_RESTAURANT_CUISINE_PCT = 30.0
MIN_RESTAURANTS = 5000
MIN_NAMED_ATTRACTIONS = 5000
MIN_ATTRACTION_NAMED_PCT = 40.0
MIN_LATIN_NAME_PCT = 90.0

REVIEW_SAMPLE_SIZE = 10


def pct(part: int, whole: int) -> float | None:
    """A percentage for display, rounded to one decimal. Gates never use this: see ``ratio``."""
    return None if whole == 0 else round(100.0 * part / whole, 1)


def ratio(part: int, whole: int) -> float | None:
    """The exact percentage. A gate compares this, so 89.98 % can never pass a 90 % gate."""
    return None if whole == 0 else 100.0 * part / whole


@dataclass
class KindStats:
    total: int = 0
    named: int = 0
    named_latin: int = 0
    with_cuisine: int = 0
    with_wikidata: int = 0
    with_name_en: int = 0

    def add(self, place: PlaceRow) -> None:
        self.total += 1
        if place.name is not None:
            self.named += 1
            if has_latin_letters(place.name):
                self.named_latin += 1
        if place.profile is not None and place.profile.cuisines:
            self.with_cuisine += 1
        if place.signal.wikidata_id is not None:
            self.with_wikidata += 1
        if place.names_i18n and "en" in place.names_i18n:
            self.with_name_en += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "named": self.named,
            "named_pct": pct(self.named, self.total),
            "named_with_latin_letters": self.named_latin,
            "latin_name_pct": pct(self.named_latin, self.named),
            "with_cuisine": self.with_cuisine,
            "cuisine_pct": pct(self.with_cuisine, self.total),
            "with_wikidata": self.with_wikidata,
            "wikidata_pct": pct(self.with_wikidata, self.total),
            "with_name_en": self.with_name_en,
        }


@dataclass
class Counters:
    """What an import saw: kept places per kind and category, and every exclusion."""

    kinds: dict[str, KindStats] = field(default_factory=dict)
    categories: Counter[tuple[str, str]] = field(default_factory=Counter)
    excluded: Counter[tuple[str, str]] = field(default_factory=Counter)
    not_candidates: int = 0
    areas: int = 0
    # (class, "kept" or "excluded") -> heap of (hash, entry): the 10 smallest hashes are the sample
    _samples: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = field(default_factory=dict)

    def kept(self, place: PlaceRow) -> None:
        self.kinds.setdefault(place.kind, KindStats()).add(place)
        self.categories[(place.kind, place.category)] += 1
        self._sample(place.osm_class, "kept", place.source_ref, place.source_tags)

    def exclude(
        self, decision: Decision, ref: str, tags: dict[str, str], reason: str | None = None
    ) -> None:
        why = reason or decision.reason
        self.excluded[(decision.osm_class, why)] += 1
        self._sample(decision.osm_class, f"excluded:{why}", ref, tags)

    def _sample(self, osm_class: str, outcome: str, ref: str, tags: dict[str, str]) -> None:
        """Keep a deterministic sample for classes whose rule the owner reviews (ADR 011)."""
        if osm_class not in REVIEW_CLASSES:
            return
        heap = self._samples.setdefault((osm_class, outcome), [])
        key = md5(ref.encode()).hexdigest()  # noqa: S324 - ordering only, not security
        entry = {"ref": ref, "tags": dict(sorted(tags.items()))}
        heap.append((key, entry))
        heap.sort(key=lambda item: item[0])
        del heap[REVIEW_SAMPLE_SIZE:]

    def review_sample(self) -> dict[str, list[dict[str, Any]]]:
        return {
            f"{cls} / {outcome}": [entry for _, entry in heap]
            for (cls, outcome), heap in sorted(self._samples.items())
        }

    def kind_total(self, kind: str) -> int:
        return self.kinds[kind].total if kind in self.kinds else 0

    def excluded_rows(self) -> list[dict[str, Any]]:
        return [
            {"class": cls, "reason": reason, "count": n}
            for (cls, reason), n in sorted(
                self.excluded.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
            )
        ]

    def category_rows(self, limit: int = 40) -> list[dict[str, Any]]:
        rows = sorted(self.categories.items(), key=lambda kv: (-kv[1], kv[0]))
        return [{"kind": k, "category": c, "count": n} for (k, c), n in rows[:limit]]


@dataclass(frozen=True)
class Check:
    label: str
    value: float | int | bool | None  # shown to two decimals; ``passed`` uses the exact value
    threshold: float | int | bool
    passed: bool


@dataclass(frozen=True)
class Gate:
    number: int
    name: str
    checks: list[Check]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.number,
            "name": self.name,
            "passed": self.passed,
            "checks": [
                {"label": c.label, "value": c.value, "threshold": c.threshold, "passed": c.passed}
                for c in self.checks
            ],
        }


def _at_least(label: str, value: float | int | None, threshold: float | int) -> Check:
    shown = round(value, 2) if isinstance(value, float) else value
    return Check(label, shown, threshold, value is not None and value >= threshold)


def evaluate_gates(counters: Counters, geo_bytes: int) -> list[Gate]:
    """The six gates of ADR 009, in its order."""
    restaurants = counters.kinds.get("restaurant", KindStats())
    attractions = counters.kinds.get("attraction", KindStats())
    latin_checks = [
        _at_least(
            f"{kind}: names with Latin letters (%)",
            ratio(stats.named_latin, stats.named),
            MIN_LATIN_NAME_PCT,
        )
        for kind, stats in (("restaurants", restaurants), ("attractions", attractions))
    ]
    if DISPLAY_RULE_IMPLEMENTED:
        latin_checks = [Check("a display rule is implemented", True, True, True)]
    return [
        Gate(
            1,
            "Restaurants with a name",
            [
                _at_least(
                    "named (%)",
                    ratio(restaurants.named, restaurants.total),
                    MIN_RESTAURANT_NAMED_PCT,
                )
            ],
        ),
        Gate(
            2,
            "Restaurants with a cuisine",
            [
                _at_least(
                    "with cuisine (%)",
                    ratio(restaurants.with_cuisine, restaurants.total),
                    MIN_RESTAURANT_CUISINE_PCT,
                )
            ],
        ),
        Gate(
            3, "Enough restaurants", [_at_least("restaurants", restaurants.total, MIN_RESTAURANTS)]
        ),
        Gate(
            4,
            "Named attractions",
            [
                _at_least("named attractions", attractions.named, MIN_NAMED_ATTRACTIONS),
                _at_least(
                    "attractions named (%)",
                    ratio(attractions.named, attractions.total),
                    MIN_ATTRACTION_NAMED_PCT,
                ),
            ],
        ),
        Gate(5, "Names displayable", latin_checks),
        Gate(
            6,
            "Size of the geo data",
            [
                Check(
                    "geo schema size (bytes, all regions)",
                    geo_bytes,
                    GEO_SIZE_LIMIT_BYTES,
                    geo_bytes <= GEO_SIZE_LIMIT_BYTES,
                )
            ],
        ),
    ]


def render_markdown(report: dict[str, Any]) -> str:
    """The report as Markdown, for the workflow summary and the artifact."""
    run, region, source = report["run"], report["region"], report["source"]
    out = [
        f"# Region import report: {region['name']} (`{region['id']}`)",
        "",
        f"- Import run `{run['id']}`, importer {run['importer_version']}, "
        f"selection rules {run['rules_version']}",
        f"- Source: {source['url'] or 'local file'}; SHA-256 `{source['sha256']}`; "
        f"{source['bytes']} bytes; OSM snapshot {source['osm_snapshot_date'] or 'unknown'}",
        f"- Region status after this import: **{report['region_status']}** "
        f"(all gates passed: {'yes' if report['all_gates_passed'] else 'no'})",
        "",
        "## Readiness gates (ADR 009)",
        "",
        "| # | Gate | Check | Value | Threshold | Result |",
        "|---|---|---|---:|---:|---|",
    ]
    for gate in report["gates"]:
        for check in gate["checks"]:
            value = "unknown" if check["value"] is None else check["value"]
            out.append(
                f"| {gate['gate']} | {gate['name']} | {check['label']} | {value} | "
                f"{check['threshold']} | {'pass' if check['passed'] else '**FAIL**'} |"
            )
    out += ["", "## Places kept", ""]
    out += [
        "| Kind | Total | Named | Named % | Latin names % | With cuisine % | With Wikidata % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for kind, stats in sorted(report["kinds"].items()):
        out.append(
            f"| {kind} | {stats['total']} | {stats['named']} | {stats['named_pct']} | "
            f"{stats['latin_name_pct']} | {stats['cuisine_pct']} | {stats['wikidata_pct']} |"
        )
    rule = report.get("proximity_rule")
    if rule:
        out += [
            "",
            f"Restaurants and cafes are kept within {rule['radius_m']} m of one of "
            f"{rule['attraction_anchors']} attractions, or within {rule['town_radius_m']} m of one of "
            f"{rule['town_anchors']} towns of {rule['town_min_population']} or more inhabitants.",
        ]
    out += ["", f"Administrative areas imported: {report['admin_areas']}", ""]
    out += ["## Excluded objects by class", "", "| Class | Reason | Count |", "|---|---|---:|"]
    for row in report["excluded"]["by_class"]:
        out.append(f"| `{row['class']}` | {row['reason']} | {row['count']} |")
    out.append(f"\nTotal excluded: {report['excluded']['total']}\n")
    out += ["## Largest categories kept", "", "| Kind | Category | Count |", "|---|---|---:|"]
    for row in report["categories"][:20]:
        out.append(f"| {row['kind']} | {row['category']} | {row['count']} |")
    out += [
        "",
        f"Geo schema size: {report['geo_size_bytes']} bytes (gate 6 limit {GEO_SIZE_LIMIT_BYTES}).",
        "",
    ]
    if report["warnings"]:
        out += ["## Warnings", ""] + [f"- {w}" for w in report["warnings"]] + [""]
    return "\n".join(out)


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
