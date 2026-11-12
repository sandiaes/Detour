"""Spike S2 (throwaway): combine per-country CSV files into one Markdown report.

Usage: python3 -I report.py <results-dir> > report.md
Reads <results-dir>/<slug>/{files,quality,subclass,size}.csv. Computes percentages and
totals only; missing data stays missing.
"""
import csv
import sys
from pathlib import Path

SUPABASE_FREE_DB_MB = 500  # docs/app-plan.md section 1, read 2026-11-12


def rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def mb(n):
    return f"{int(n) / 1_000_000:,.1f}"


def pct(part, whole):
    whole = int(whole)
    return "n/a" if whole == 0 else f"{100 * int(part) / whole:.0f}%"


def main(root):
    countries = sorted(p for p in Path(root).iterdir() if (p / "size.csv").exists())
    out = ["# Spike S2 results", ""]

    out += ["## Extract and import sizes", "",
            "| Country | Extract (MB) | Filtered (MB) | Rows | Table+indexes (MB) | Download s | Filter s | Import s |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    total_bytes = 0
    for c in countries:
        f = rows(c / "files.csv")[0]
        s = rows(c / "size.csv")[0]
        total_bytes += int(s["total_bytes"])
        out.append(f"| {c.name} | {mb(f['source_bytes'])} | {mb(f['filtered_bytes'])} | "
                   f"{int(s['rows']):,} | {mb(s['total_bytes'])} | {f['download_s']} | "
                   f"{f['filter_s']} | {f['import_s']} |")
    out += ["", f"Total table+indexes for the countries above: **{mb(total_bytes)} MB**. "
            f"Supabase Free database limit: {SUPABASE_FREE_DB_MB} MB (docs/app-plan.md, read 2026-11-12). "
            "This is a spike schema, not the final `geo` schema, and it excludes the `app` schema "
            "and database overhead, so it is an estimate.", ""]

    for cls in ("attraction", "restaurant"):
        out += [f"## Quality: {cls}", "",
                "| Country | Total | Named | Name EN | Name Latin | Name w/o Latin | Cuisine | Wikidata | Website |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for c in countries:
            r = next((x for x in rows(c / "quality.csv") if x["class"] == cls), None)
            if r is None:
                out.append(f"| {c.name} | 0 | | | | | | | |")
                continue
            t = r["total"]
            out.append(f"| {c.name} | {int(t):,} | {int(r['with_name']):,} ({pct(r['with_name'], t)}) | {pct(r['with_name_en'], t)} | "
                       f"{pct(r['with_name_latin'], t)} | {pct(r['name_without_latin_letters'], t)} | "
                       f"{pct(r['with_cuisine'], t)} | "
                       f"{pct(r['with_wikidata'], t)} | {pct(r['with_website'], t)} |")
        out.append("")

    out += ["## Excluded by the ADR 003 selection rule", ""]
    for c in countries:
        ex = rows(c / "excluded.csv")
        total = sum(int(r["total"]) for r in ex)
        out.append(f"**{c.name}:** {total:,} excluded; " + ", ".join(f"{r['subclass']} {int(r['total']):,}" for r in ex[:6]))
        out.append("")
    out += ["## Most common subclasses", ""]
    for c in countries:
        top = rows(c / "subclass.csv")[:10]
        out.append(f"**{c.name}:** " + ", ".join(f"{r['class']}/{r['subclass']} {int(r['total']):,}" for r in top))
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
