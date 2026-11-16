# Backups

Supabase Free makes **no backups** (ADR 005, decision 5). This page says what is backed up, how to
restore it, and what is not covered. Written in Phase 9 (2026-11-15).

## 1. Two kinds of backup, for two kinds of loss

| | "Back up app data" (GitHub Actions) | "Back up all trips" (the app) |
|---|---|---|
| Protects against | Losing the database: a deleted or broken Supabase project, a bad migration, a mistake in SQL | Losing the phone or the app: a reinstall, a new phone, a new signing key |
| Contains | The whole `app` schema: every installation's trips, plans, versions, own places, stays, visits, change sets | Your trips as `.detour` files: each trip's chosen plan (or past record), stops, times, cities, and, if chosen, **the documents** |
| Documents on the phone | **No** (they are never on the server) | **Yes**, when "Include documents" is on |
| Runs | Every day at 02:17 UTC, and by hand | When you tap it |
| Kept | 30 days, as encrypted workflow artifacts (in a public repository anyone with read access can download them, hence the encryption) | Wherever you save the file |
| Restores into | The same database, replacing `app` | A new copy of each trip, under the phone's installation (ADR 028) |
| Encryption | Always: AES-256 with the secret `DETOUR_BACKUP_PASSPHRASE` (the run fails without it; the repository is public) | None: the file is a plain zip (ADR 028); keep it private |

Use both. Before the 2026-11-17 trip, and before any reinstall or key change, do **More, Back up
all trips** with documents and keep the file off the phone (Drive, email to yourself, a computer).

## 2. The daily database backup

Workflow: [`.github/workflows/backup-app-data.yml`](../.github/workflows/backup-app-data.yml).

**Set up once:**

1. The secret `DETOUR_IMPORT_DATABASE_URL` already exists if a region was imported (the Supabase
   *session pooler* string, port 5432). The backup uses the same one.
2. **Required:** GitHub, the repository, Settings, Secrets and variables, Actions, New repository
   secret `DETOUR_BACKUP_PASSPHRASE` with a long random passphrase from your password manager. The
   run refuses to upload anything without it: the repository is public (2026-11-15), and GitHub
   shows Actions logs to everyone and lets anyone with read access download artifacts (GitHub Docs,
   "Setting repository visibility" and "Downloading workflow artifacts", read 2026-11-15). The run's
   public summary shows only the schema version and the dump's size.
3. Merge the workflow into `main`: scheduled workflows run only from the default branch.
4. Run it once by hand: Actions, "Back up app data", Run workflow. The run's summary lists the schema
   version; the artifact `app-backup-<date>` holds `app.dump.gpg`, `row-counts.txt.gpg` (the row
   count of every `app` table) and `schema-version.txt`.

**Also keeps Supabase awake:** the daily connection counts as activity, so a Free project is not
paused after low activity over 7 days. The UptimeRobot monitor (every 5 minutes, `deployment.md`) does the same job more often.

**Not running?** Standard runners are free in a public repository ("The use of standard GitHub-hosted
runners is free: In public repositories", GitHub Docs, Actions billing, read 2026-11-15). But "In a
public repository, scheduled workflows are automatically disabled when no repository activity has
occurred in 60 days" (GitHub Docs, "Disabling and enabling a workflow", read 2026-11-15): after two
months without a commit, open Actions, "Back up app data", and **Enable workflow**. On 2026-11-15,
while the repository was still private, Actions stopped starting jobs (minutes used up; see
[`audit-phase-9.md`](audit-phase-9.md)).

## 3. Restoring the database

Tried on a scratch database in Phase 9 (a trip with stops, times and a stay came back identical).
It replaces **all** of `app`, so everything written after the backup is lost. Do it from a computer
with the PostgreSQL 17 client, or ask the assistant to do it in a cloud session.

1. **Stop the API** so nothing writes during the restore: Render, the `detour-api` service,
   Settings, Suspend.
2. Download the artifact and, if encrypted, decrypt it:
   `gpg --decrypt app.dump.gpg > app.dump` (asks for the passphrase).
3. Check the schema version in `schema-version.txt` against the database
   (`SELECT version_num FROM public.alembic_version`). They must be equal; if the database is newer,
   restore into a database at that version (check out the matching commit and run `alembic upgrade`
   to that revision) or ask for help.
4. In Supabase's SQL editor: `DROP SCHEMA app CASCADE;`
5. Restore through the session pooler:
   `pg_restore --dbname "<session pooler string>" --no-owner --no-privileges --single-transaction --exit-on-error app.dump`
6. Resume the service on Render and open the app: the trips come back under the same installation
   (the token on the phone did not change).

`geo` is not in the backup: the "Import region" workflow rebuilds it, and `app` refers to it by
identifier only. After a re-import, stops snapshot their name and point, so a plan still reads; a
restored itinerary version that points at a place the new import no longer has keeps its snapshot.

## 4. What is not covered

- **Documents on the phone**, unless exported with "Back up all trips" (they never reach the server).
- The photo files in Supabase Storage (rebuilt by "Resolve images" and the background resolver).
- **Covers chosen from a phone** in the private `trip-files` bucket (ADR 034, step 5): the daily
  backup has their rows, not the pictures. The phones that showed a cover keep a copy.
- Render's settings and secrets (written down in [`deployment.md`](deployment.md)).
- Anything older than 30 days in the Actions backup.
