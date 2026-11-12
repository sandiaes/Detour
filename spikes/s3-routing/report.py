"""Spike S3 (throwaway): turn the raw S3 output into a Markdown report.

Usage: python3 -I report.py <out/slug directory> > report.md
Only measured values are printed; anything missing is shown as unknown.
"""
import json
import re
import sys
from pathlib import Path


def kv(path):
    data = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v
    return data


def mb(n):
    return f"{int(n) / 1_000_000:,.1f}"


def main(d):
    d = Path(d)
    env = kv(d / "env.txt")
    time_txt = (d / "build_time.txt").read_text(encoding="utf-8")
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", time_txt)
    status = re.search(r"Exit status: (\d+)", time_txt)
    bench_path = d / "bench.json"
    out = [f"# Spike S3 results: {d.name}", "",
           "## Machine", "",
           f"- CPUs: {env['runner_cpus']}, RAM: {env['runner_mem_mb']} MB, "
           f"free disk at start: {env['runner_disk_free_mb']} MB",
           f"- pyvalhalla {env['pyvalhalla']}", "",
           "## Tile build", "",
           f"- Extract: {mb(env['pbf_bytes'])} MB, downloaded in {env['download_s']} s",
           f"- Build time: {env['build_s']} s",
           f"- Peak memory of the build: {int(rss.group(1)) / 1024:,.0f} MB" if rss else "- Peak memory: unknown",
           f"- Build exit status: {status.group(1) if status else 'unknown'}",
           f"- Tiles on disk: {mb(env['tiles_bytes'])} MB in {env['tile_files']} files", ""]
    if bench_path.exists() and bench_path.stat().st_size:
        b = json.loads(bench_path.read_text(encoding="utf-8"))
        out += ["## Matrix benchmark (50 x 50)", "",
                f"- Graph load: {b['actor_load_s']} s; process memory before load "
                f"{b['peak_rss_mb_before_load']} MB",
                "- Service limits were raised for the benchmark (see make_config.py).", "",
                "| Case | Warm-up ms | Median ms | Min ms | Max ms | Unreachable cells | Peak process MB | Error |",
                "|---|---:|---:|---:|---:|---:|---:|---|"]
        for c in b["cases"]:
            out.append(f"| {c['case']} | {c.get('warmup_ms', '')} | {c.get('median_ms', '')} | "
                       f"{c.get('min_ms', '')} | {c.get('max_ms', '')} | "
                       f"{c.get('unreachable_cells', '')} of {c.get('cells', '')} | "
                       f"{c['peak_rss_mb_after']} | {c['error'] or ''} |")
    else:
        out += ["## Matrix benchmark", "", "Not run (the build did not finish)."]
    out += ["", "Notes: built without the optional admin and timezone databases. "
            "Timings are for one runner and are not a hosting guarantee."]
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
