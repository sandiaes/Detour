#!/usr/bin/env bash
# Spike S3 (throwaway): build Valhalla tiles from one Geofabrik extract and benchmark
# 50 x 50 matrices. Writes results to out/<slug>/.
#
# Usage: run.sh <slug> <geofabrik-path> <bench-lat> <bench-lon>
# Env:   LOCAL_PBF  use this file instead of downloading (tests)
#        OUT_DIR, WORK_DIR  default ./out and ./work
# Needs: pyvalhalla installed in the active Python, GNU time at /usr/bin/time
set -euo pipefail

slug="$1"; path="$2"; lat="$3"; lon="$4"
here="$(cd "$(dirname "$0")" && pwd)"
out="${OUT_DIR:-$PWD/out}/$slug"
work="${WORK_DIR:-$PWD/work}/$slug"
ua="Detour-spike-S3/0.1 (+https://github.com/sandiaes/Detour)"
src="https://download.geofabrik.de/${path}-latest.osm.pbf"
pbf="$work/source.osm.pbf"
tiles="$work/tiles"
cfg="$work/valhalla.json"

mkdir -p "$out" "$work"

{
    echo "runner_cpus=$(nproc)"
    echo "runner_mem_mb=$(free -m | awk '/^Mem:/ {print $2}')"
    echo "runner_disk_free_mb=$(df -m "$work" | awk 'NR==2 {print $4}')"
    echo "pyvalhalla=$(python3 -I -m pip show pyvalhalla | awk '/^Version:/ {print $2}')"
} > "$out/env.txt"

t0=$(date +%s)
if [ -n "${LOCAL_PBF:-}" ]; then
    cp "$LOCAL_PBF" "$pbf"
else
    curl -fsSL --retry 3 --retry-delay 10 -A "$ua" -o "$pbf" "$src"
fi
t1=$(date +%s)

mkdir -p "$tiles"
python3 -I "$here/make_config.py" "$tiles" "$cfg"

# GNU time -v reports "Maximum resident set size" for the build.
/usr/bin/time -v -o "$out/build_time.txt" \
    python3 -I -m valhalla valhalla_build_tiles -c "$cfg" "$pbf" \
    > "$out/build_log.txt" 2>&1
t2=$(date +%s)

{
    echo "pbf_bytes=$(stat -c %s "$pbf")"
    echo "tiles_bytes=$(du -sb "$tiles" | cut -f1)"
    echo "tile_files=$(find "$tiles" -type f | wc -l)"
    echo "download_s=$((t1 - t0))"
    echo "build_s=$((t2 - t1))"
} >> "$out/env.txt"

python3 -I "$here/bench.py" "$cfg" "$lat" "$lon" > "$out/bench.json"
tail -n 40 "$out/build_log.txt" > "$out/build_log_tail.txt"
rm -f "$out/build_log.txt"
rm -rf "$work"
echo "done: $slug"
