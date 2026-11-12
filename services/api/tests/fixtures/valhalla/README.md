# Valhalla fixtures

`*-recorded.json` are **real responses** from the FOSSGIS server, recorded by the owner by hand on
2026-11-12 (`docs/spikes/fossgis-request-shape-check.md`, requests A, B, G, H): a 1 x 1 and a 1 x 10
walking matrix, and a plain and a `directions_type: none` walking route, in Florence. Never
re-recorded by a test or by CI.

`*-documented.json` are **not recordings**: they follow the same format for cases the owner has not
recorded yet (a null cell, and a long driving route; figures are the ones the owner reported in
`docs/spikes/fossgis-matrix-check.md`, otherwise illustrative). Replace them when a real
recording exists.
