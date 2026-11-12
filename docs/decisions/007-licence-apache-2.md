# ADR 007 — Licence for the Detour source code: Apache-2.0

- **Status:** Accepted on 2026-11-12 (owner approval). Decides D11.
- **Date:** 2026-11-12
- **Related:** [`../app-plan.md`](../app-plan.md) (D1, D11), [`005-free-managed-hosting.md`](005-free-managed-hosting.md),
  [`008-no-app-stores.md`](008-no-app-stores.md)

## Context

D1 makes Detour open source and non-commercial. An open-source licence cannot itself forbid
others' commercial use (app plan, note on D1), so "non-commercial" describes how the owner
operates the app, not what the licence allows. Transitous (public transport, Phase 10) requires
published source under an open-source licence. A public repository makes standard GitHub-hosted
runners free (ADR 005, from GitHub's billing page read 2026-11-12), which matters for a
free-only project.

## Decision

1. The Detour source code is licensed under the **Apache License 2.0**.
2. The `LICENSE` file is added to the repository root, copied from the official text
   (<https://www.apache.org/licenses/LICENSE-2.0.txt>), when the owner decides to make the
   repository public. Until then the repository stays private.
3. Licence of the code is separate from the licence of the data. OpenStreetMap data stays under
   ODbL and remains stored as separate source records (data model, section 5).
4. This is not legal advice. A legal review stays on the list for any commercial release
   (app plan, risks).

## Checklist before the repository becomes public

- Check the author names and email addresses visible in the git history; use GitHub's private
  "noreply" address if the owner prefers.
- Confirm that no secret, key or personal data is in the repository or its history.
- Confirm the owner is comfortable with the planning documents and ADRs being visible.
- Add `LICENSE` and a short licence notice to the README.

## Alternatives

| Alternative | Why not |
|---|---|
| MIT | Also permissive and shorter, but without Apache-2.0's explicit patent grant. Acceptable if the owner prefers it. |
| GPL-3.0 or AGPL-3.0 | Copyleft; more restrictive for others. AGPL would only matter if closed hosted copies of the server were a worry, which is unlikely for a personal, free-only app. |

## Consequences

- D11 is decided. The only open step is when to make the repository public.
- A public repository gives free standard runners (4 CPUs, 16 GB RAM per GitHub's page) for the
  import and build workflows.
