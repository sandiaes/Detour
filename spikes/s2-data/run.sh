#!/usr/bin/env bash
# Spike S2 (throwaway): download one Geofabrik extract, filter it, import it into
# PostGIS and write quality and size numbers as CSV.
#
# Usage: run.sh <slug> <geofabrik-path>      e.g. run.sh austria europe/austria
# Env:   PGHOST PGPORT PGUSER PGPASSWORD   database connection (libpq variables)
#        LOCAL_PBF                          use this file instead of downloading (tests)
#        OUT_DIR, WORK_DIR                  default ./out and ./work
set -euo pipefail

slug="$1"
path="$2"
here="$(cd "$(dirname "$0")" && pwd)"
out="${OUT_DIR:-$PWD/out}/$slug"
work="${WORK_DIR:-$PWD/work}/$slug"
db="s2_${slug//-/_}"
ua="Detour-spike-S2/0.1 (+https://github.com/sandiaes/Detour)"
src="https://download.geofabrik.de/${path}-latest.osm.pbf"
pbf="$work/source.osm.pbf"
filtered="$work/filtered.osm.pbf"

mkdir -p "$out" "$work"

t0=$(date +%s)
if [ -n "${LOCAL_PBF:-}" ]; then
    cp "$LOCAL_PBF" "$pbf"
    echo "local test file" > "$out/headers.txt"
else
    curl -fsSIL -A "$ua" "$src" > "$out/headers.txt"
    curl -fsSL --retry 3 --retry-delay 10 -A "$ua" -o "$pbf" "$src"
fi
t1=$(date +%s)

# Keep only what Detour needs. Referenced nodes and ways are kept by default.
osmium tags-filter "$pbf" \
    nwr/tourism=attraction,museum,gallery,viewpoint,zoo,theme_park,aquarium \
    nwr/historic \
    nwr/amenity=restaurant,cafe \
    -o "$filtered" --overwrite
t2=$(date +%s)

psql -d postgres -v ON_ERROR_STOP=1 -qc "DROP DATABASE IF EXISTS $db"
psql -d postgres -v ON_ERROR_STOP=1 -qc "CREATE DATABASE $db"
psql -d "$db" -v ON_ERROR_STOP=1 -qc "CREATE EXTENSION postgis"
osm2pgsql -d "$db" --output=flex --style="$here/import.lua" --cache=1000 "$filtered"
t3=$(date +%s)

psql -d "$db" -v ON_ERROR_STOP=1 -qc "VACUUM ANALYZE poi"
psql -d "$db" -v ON_ERROR_STOP=1 --csv -f "$here/quality.sql" > "$out/quality.csv"
psql -d "$db" -v ON_ERROR_STOP=1 --csv -f "$here/subclass.sql" > "$out/subclass.csv"
psql -d "$db" -v ON_ERROR_STOP=1 --csv -f "$here/size.sql" > "$out/size.csv"

{
    echo "slug,source_url,source_bytes,filtered_bytes,download_s,filter_s,import_s"
    echo "$slug,$src,$(stat -c %s "$pbf"),$(stat -c %s "$filtered"),$((t1 - t0)),$((t2 - t1)),$((t3 - t2))"
} > "$out/files.csv"

psql -d postgres -qc "DROP DATABASE IF EXISTS $db"
rm -rf "$work"
echo "done: $slug"
