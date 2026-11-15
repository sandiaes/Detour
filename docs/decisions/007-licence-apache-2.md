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
2. The `LICENSE` file was added to the repository root on 2026-11-12, copied unchanged from the
   official text (<https://www.apache.org/licenses/LICENSE-2.0.txt>, 11,358 bytes). The
   repository stays private until the owner decides to publish it.
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

## Addendum of 2026-11-15: the repository is made public

The owner decided on 2026-11-15 to make the repository public ("lets turn the repo public, Ive hit
my limit"): the private repository's Actions minutes were used up, so no CI, APK build or backup
could run. Standard runners are free in a public repository ("The use of standard GitHub-hosted
runners is free: In public repositories", GitHub Docs, Actions billing, read 2026-11-15). The owner
changes the visibility in the repository's settings; nothing in the code does.

The checklist above, done in the Phase 9 session before the switch:

- **Secrets in the history:** none. All 156 commits of every branch were searched for keys, tokens,
  passwords, connection strings and the Supabase project reference; only test placeholders
  (`sb_secret_x`) and the documented example address match. No `.env`, keystore or key file was
  ever committed (`.env.example` only).
- **Author names and email addresses:** the history shows the owner's commit email addresses (two
  personal or work addresses besides GitHub's and Anthropic's noreply addresses). They cannot be
  hidden after publication without rewriting the history; the owner decides. Future commits can use
  GitHub's noreply address (GitHub, Settings, Emails, "Keep my email addresses private").
- **Personal data in the files:** none found; the reference screens in `docs/screenshots/` are
  invented mock-ups.
- **`LICENSE` and the README notice:** present since 2026-11-12.

What changes with publication (GitHub Docs, "Setting repository visibility", read 2026-11-15):
"Actions history and logs will be visible to everyone", "Anyone can fork your repository", and
artifacts can be downloaded by anyone with read access. Hence, in the same change: the "Back up app
data" workflow refuses to upload anything without its encryption passphrase and keeps even its row
counts encrypted; "Create signing key" writes the key straight into the repository's secrets
instead of an artifact; the APK artifact (which contains the backend's address) is accepted as
public, protected by the API's request limits. Secrets stay hidden: fork pull requests get none, and
CI runs only on pushes to this repository. The User-Agent contact link
(`https://github.com/sandiaes/Detour`) now resolves for the providers (Photon, FOSSGIS, Wikimedia).
"In a public repository, scheduled workflows are automatically disabled when no repository activity
has occurred in 60 days" (GitHub Docs, read 2026-11-15): the daily backup must then be re-enabled
by hand.
