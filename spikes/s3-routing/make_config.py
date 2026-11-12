"""Spike S3 (throwaway): write a Valhalla config for building and benchmarking.

Usage: python3 make_config.py <tile_dir> <out.json>
The matrix limits are raised so the benchmark measures speed, not the default request
limits. Those raised limits are recorded in the report.
"""
import json
import sys

from valhalla import get_config

tile_dir, out = sys.argv[1], sys.argv[2]
config = get_config(tile_extract="", tile_dir=tile_dir, verbose=True)
for costing in ("auto", "pedestrian"):
    limits = config["service_limits"][costing]
    limits["max_matrix_distance"] = 10_000_000
    limits["max_matrix_location_pairs"] = 2500
    limits["max_locations"] = 50
with open(out, "w", encoding="utf-8") as fh:
    json.dump(config, fh, indent=2)
print("wrote", out)
