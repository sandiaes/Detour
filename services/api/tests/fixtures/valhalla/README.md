# Valhalla fixtures

**These are not live recordings.** The build environment cannot reach the FOSSGIS server and the
Valhalla API reference could not be read there (ADR 013). The files follow the response format
the owner pasted on 2026-11-12 (`sources_to_targets`, `distance` in kilometres, `time` in seconds,
`trip.summary.length` and `.time`) and the format described in ADR 013. Numbers are those the
owner reported where one exists (0.662 km in 523 s; Florence to Rome 282.885 km in 11,505 s) and
otherwise illustrative.

Replace them with real recordings after the owner's check
(`docs/spikes/fossgis-request-shape-check.md`) and rerun the contract tests.
