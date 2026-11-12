"""Spike S5 (throwaway): merge bench.py results from several machines into one Markdown report.

Usage: python3 -I report.py <result.json> [<result.json> ...] > report.md
"""
import json
import sys


def main():
    runs = []
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            runs.append(json.load(f))
    print("## Machines\n")
    print("| Label | Platform | CPU | CPUs | Python | OR-Tools | lns_time_limit default (ms) |")
    print("|---|---|---|---:|---|---|---:|")
    for r in runs:
        e = r["env"]
        print(f"| {r['label']} | {e['platform']} | {e['cpu']} | {e['cpus']} | {e['python']} "
              f"| {e['ortools']} | {e['ortools_defaults']['lns_time_limit_ms']} |")
    keys = []
    for c in runs[0]["cases"]:
        keys.append((c["fixture"], c["method"]))
    by = [{(c["fixture"], c["method"]): c for c in r["cases"]} for r in runs]

    print("\n## Quality (first machine)\n")
    print("| Fixture | Method | Valid | Objective | Visits | Score | Travel min | Travel share "
          "| Utilisation |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for k in keys:
        c = by[0][k]
        m = c["metrics"]
        print(f"| {k[0]} | {k[1]} | {'yes' if c['valid'] else 'NO'} | {m['objective']} "
              f"| {m['visits']} | {m['score']} | {m['travel_min']} | {m['travel_share']} "
              f"| {m['utilisation']} |")

    print("\n## Latency, median ms per solve\n")
    print("| Fixture | Method | " + " | ".join(r["label"] for r in runs) + " |")
    print("|---|---|" + "---:|" * len(runs))
    for k in keys:
        cells = [str(b[k]["median_ms"]) if k in b else "n/a" for b in by]
        print(f"| {k[0]} | {k[1]} | " + " | ".join(cells) + " |")

    print("\n## Repeatability\n")
    print("Distinct plans within each machine's repeated runs, and whether every run on every "
          "machine produced the same plan.\n")
    print("| Fixture | Method | " + " | ".join(r["label"] for r in runs)
          + " | Same plan everywhere |")
    print("|---|---|" + "---:|" * len(runs) + "---|")
    for k in keys:
        cells, allh = [], set()
        for b in by:
            if k in b:
                cells.append(str(b[k]["distinct_hashes"]))
                allh.update(b[k]["hashes"])
            else:
                cells.append("n/a")
        objs = sorted({b[k]["metrics"]["objective"] for b in by if k in b})
        same = "yes" if len(allh) == 1 else f"NO ({len(allh)} plans, objectives {objs})"
        print(f"| {k[0]} | {k[1]} | " + " | ".join(cells) + f" | {same} |")


if __name__ == "__main__":
    main()
