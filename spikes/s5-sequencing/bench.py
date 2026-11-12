"""Spike S5 (throwaway): run every sequencer on every fixture several times.

Usage: python3 -I bench.py <fixtures-dir> <label> <out.json> [repeats]

Records per (fixture, method): plan quality (from the independent validator), latency of each
run, and the hash of each run's canonical plan. Identical hashes across runs and machines mean
the method is repeatable.
"""
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ortools  # noqa: E402

import common  # noqa: E402
import heuristic  # noqa: E402
import ortools_seq  # noqa: E402
import validate  # noqa: E402

METHODS = ["heuristic", "ortools:descent", "ortools:au-descent", "ortools:gls-s100",
           "ortools:au-gls-s100", "ortools:gls-s1000", "ortools:gls-t2000"]


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def run_one(p, method):
    t0 = time.perf_counter()
    if method == "heuristic":
        routes, info = heuristic.solve(p)
    else:
        routes, info = ortools_seq.solve(p, method.split(":", 1)[1])
    ms = (time.perf_counter() - t0) * 1000
    return routes, info, ms


def main():
    fixtures_dir, label, out_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    repeats = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    methods = os.environ.get("S5_METHODS", ",".join(METHODS)).split(",")
    result = {
        "label": label,
        "env": {"platform": platform.platform(), "machine": platform.machine(),
                "cpu": cpu_name(), "cpus": os.cpu_count(),
                "python": platform.python_version(), "ortools": ortools.__version__,
                "ortools_defaults": ortools_seq.default_limits()},
        "repeats": repeats,
        "cases": [],
    }
    for path in sorted(fixtures_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            fx = json.load(f)
        p = common.Problem(fx)
        for method in methods:
            hashes, times, infos = [], [], []
            plan = None
            for _ in range(repeats):
                routes, info, ms = run_one(p, method)
                plan = common.plan_output(p, routes)
                hashes.append(common.plan_hash(plan))
                times.append(round(ms, 1))
                infos.append(info)
            errors, metrics = validate.check(fx, plan)
            mismatch = any(d["events"] is None for d in plan["days"])
            case = {"fixture": fx["name"], "method": method, "hashes": hashes,
                    "distinct_hashes": len(set(hashes)), "ms": times,
                    "median_ms": statistics.median(times), "max_ms": max(times),
                    "valid": not errors, "errors": errors[:5], "schedule_mismatch": mismatch,
                    "metrics": metrics, "info": infos[-1]}
            result["cases"].append(case)
            print(f"{fx['name']:16} {method:18} obj={metrics['objective']:6} "
                  f"visits={metrics['visits']:3} travel={metrics['travel_min']:5} "
                  f"med={case['median_ms']:9.1f}ms distinct={case['distinct_hashes']} "
                  f"valid={case['valid']}", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
