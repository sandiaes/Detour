# Prompt: manual transport legs (Option B), plus the note for Option D

Paste everything below the line into a new Claude Code session on this repository.

---

You are working on Detour (read `CLAUDE.md` first and follow it exactly). Your task is **design first, then build**, for one feature: **manual transport legs**. The owner reviewed an analysis of public transport on 2026-11-16 and chose this option. Do not start Phase 10 (routing through Transitous or MOTIS) and do not add any provider.

## Why

Detour is a trip manager and travel history first (ADR 026). The owner almost never generates itineraries. Public transport today is only a dead pill: on the new-trip screen "Public transport" is local state, not sent, not stored, ignored by the planner (`apps/mobile/src/screens/CreateTripScreen.tsx`, around lines 103 to 105 and 582 to 594). The Add sheet has a disabled "Transport" row. Travel between stops is walk or drive only (`planner/travel.py`, `adapters/valhalla.py`). Between cities the app shows a driving time even for a train trip, and a journey into or out of Japan reads "time not calculated: public transport is not built yet". What a trip manager needs is to **record how the user actually moved**: "train Rome to Florence, 10:12, 1 h 30".

## What to build (the proposal; the ADR may refine it, ask the owner where marked)

A **transport leg** the user adds by hand:

- Mode: train, bus, metro or tram, ferry, taxi or ride, walk, other (a fixed list, with an icon each, in `components/ds` style).
- From and to: the user's stops, cities or places on the trip, or free text. A leg between two stops of a day, or a journey between two cities (ADR 024).
- Day, start time, duration (or arrival time). All entered by the user. Optional note. Optional link to a document (ADR 023: a ticket or booking) from the existing document links.
- It is **fixed**: Optimize (ADR 029) and recalculation (ADR 018) never move it or reorder across it, and they use its duration as the real travel time for that leg instead of a walk or drive time.
- It replaces the computed leg it covers in the day list and the map (a line with the mode icon, "Train · 1 h 30"), and it fills the "time not calculated" gap for a journey between cities, including Japan.
- Never invent values: a duration the user did not enter is unknown and shown as unknown (hard constraint 5). No prices (ADR 017), no booking (hard constraint 2).
- Export and import carry it (ADR 028, a new version of the trip file if needed; check how stays were left out and decide on purpose). Undo and itinerary versions work as for any other edit.

Also decide and record in the ADR (ask the owner if unsure):

1. **The dead "Public transport" pill.** Recommended: remove it, with its hint text, tests, the accessibility test line and the lines in `docs/design.md` (section 3, "Getting around", and the open point in section 7), `docs/design-audit.md`, `docs/known-limitations.md`, ADR 021 (decisions 92 and 99, as an amendment, not a rewrite) and `CLAUDE.md`. Keep **Car** as it is.
2. **Optimize without a car.** Today `uses_car` false makes Optimize walk every leg however long (`planner/optimize_service.py:96`, `repo/stays.py:220`), and `uses_car` defaults to false on creation but true in migration `0018` and on import. Analysis recommended not hiding this. Propose a rule (for example legs above a threshold are not timed as walks, or the user's transport legs and a labelled estimate are used) and ask the owner to choose before building that part.
3. Whether a leg may attach to a **stop pair** within a day, a **journey between cities**, or both in the first step.

## Process

1. Read `CLAUDE.md`, `docs/design.md`, `docs/design-audit.md`, `docs/decisions/026`, `021` (decisions 78 to 99), `023`, `024`, `028`, `029`, `030`, `docs/data-model.md`, `docs/known-limitations.md`, `docs/api-evaluation.md` section 8, and the code you will touch (planner, `repo/`, `models/`, `apps/mobile/src/components/plan/DayPlan.tsx`, `nav/BottomNav.tsx`, the Add flows, the export module).
2. **Write ADR 032** in `docs/decisions/` (status Proposed; context, decision, alternatives, consequences; follow the format of ADR 029 and 030). This is a new feature, so CLAUDE.md rule 3 applies: stop and show the owner the ADR and your open questions before you build. If the questions cannot be asked interactively, put them at the top of the ADR and build only after the owner answers.
3. After approval, build in small steps, each with tests: migration and API (and `python scripts/export_openapi.py`, then `npm run generate`), planner and Optimize behaviour (golden tests only if the engine changes; bump `CONFIG_VERSION` if so), export and import, then the app. The app must follow `docs/design.md` and pass `styleTokens.test.ts` (no own colours, sizes, radii, spacing, and the focus ring on tappable things). Add the component and accessibility tests.
4. Update every affected document in the same change (CLAUDE.md "Current state" paragraph, `design.md`, `data-model.md`, `known-limitations.md`, `app-plan.md` Phase 10 row, `product-brief.md`, `build-prompts.md` Prompt 12).
5. Run `npm run format:check`, `typecheck`, `lint`, `npm test`, and in `services/api` `ruff check`, `ruff format --check`, `mypy`, `pytest`. Report results as they are. Say plainly that nothing was checked on a device.
6. Work on a branch, commit in clear steps, and push. Do not open a pull request unless asked.

## Also do: record Option D for later (documentation only)

Add a short section so the idea is not lost, in these places and no code:

- `docs/app-plan.md`, in section 4 "After the MVP", directly under the Phase 10 row or the note after the table: **"Phase 10, narrowed (candidate, not approved): one-leg transit suggestion."**
- `docs/decisions/032-...md`, a section "Later: a suggestion for one leg".
- One line in `docs/known-limitations.md` under "Features not built": "Suggested transit time for a leg: not built; manual legs only (ADR 032)".
- Update `docs/build-prompts.md` Prompt 12 with a pointer saying it is superseded as written by this narrower candidate.

Text of the note (adapt to the document's voice):

> **Option D: suggest a time for one transport leg.** After manual transport legs exist (ADR 032), the user may ask Detour for a suggested public-transport time for **one leg**: from here to there, on this day and time. The backend asks Transitous (MOTIS 2 API) for a single journey and the app shows it as a **labelled estimate**: the user accepts it (it becomes a normal manual leg, editable) or ignores it. No planner change, no bulk routing, no use inside generation or Optimize, no real-time data. Why it fits: light use, one request per tap, well under Transitous's 720 requests a day coordination threshold; the repository is public (ADR 007 addendum), which resolves the old D11 blocker. Preconditions: an ADR citing the Transitous terms and the date read (CLAUDE.md rule 4; `docs/api-evaluation.md` section 8.1 has the verified summary and must be re-checked), an adapter with a timeout, a cache, a daily budget counter and an identifying User-Agent, a visible link to https://transitous.org/sources/ and each source's attribution, and a fallback of "no suggestion, enter it by hand". Risks: best effort service that can be withdrawn at any time (the manual leg must keep working without it), feed quality varies by region, schedule data only (a time on a day weeks ahead is a timetable, not a promise). If Transitous becomes unavailable, self-hosted MOTIS is not in scope at this size. Not approved by the owner; do not build it without a new request.

Keep the tone of the existing docs: plain, dated 2026-11-16, no marketing words.
