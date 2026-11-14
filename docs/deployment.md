# Deployment: Render (API) and Supabase (database)

Hosting is decided in [ADR 005](decisions/005-free-managed-hosting.md): the API runs as a Render
free web service, the PostgreSQL database is a Supabase Free project. This guide takes you from
nothing to an Android phone calling the deployed health endpoint. You create both accounts
yourself; do the steps in order and stop after each one to check its result.

Nothing here needs software on your computer: a web browser is enough.

## What you will have at the end

```
Phone (Detour APK) ──HTTPS──► Render free web service "detour-api" ──► Supabase Free database
                                 (FastAPI, sleeps when idle)            (schemas geo and app, empty)
```

## Facts this guide relies on

Read on 2026-11-12 from the providers' official pages. Provider pages change; if a screen below
does not match what you see, trust the screen and tell the project owner's assistant.

| Fact | Source |
|---|---|
| Render free web services spin down after 15 minutes without inbound traffic; waking takes "about one minute" | <https://render.com/docs/free> |
| 750 free instance hours per workspace per month; free services restart "at any time"; the filesystem is ephemeral | <https://render.com/docs/free> |
| No pre-deploy command on the free plan ("Available for paid web services, private services, and background workers"), so migrations run in `start.sh` | <https://render.com/docs/blueprint-spec> |
| `PYTHON_VERSION` must be a fully qualified version such as `3.13.5`; Render's own default is newer than this project supports | <https://render.com/docs/python-version> |
| Blueprint: Dashboard, **New**, **Blueprint**, connect the repository, choose the branch, **Deploy Blueprint** | <https://render.com/docs/infrastructure-as-code> |
| Supabase direct connections are IPv6 on the Free plan; the shared pooler is IPv4. For an IPv4-only host use the pooler in **session mode** (port 5432) | <https://supabase.com/docs/guides/database/connecting-to-postgres> |
| Pooler user name is `postgres.<project-ref>`; the host looks like `aws-<n>-<region>.pooler.supabase.com` and must be copied from the **Connect** dialog | same page |
| Use `sslmode=require` | same page |
| PostGIS is enabled in the dashboard under Database, Extensions, and installs into the `extensions` schema | <https://supabase.com/docs/guides/database/extensions/postgis> |

**Not confirmed** (check while you follow the steps, and report what you see):

- ~~Whether PostGIS can be enabled on the Supabase **Free** plan.~~ **Confirmed by the owner on
  2026-11-12:** it could be enabled on a Free project (step 3). The Supabase page itself does not
  mention plans. Phase 2 needs it.
- Whether Render can reach Supabase over IPv6. The Render pages do not say. This guide avoids the
  question by using the IPv4 pooler.
- The exact wording of Render's prompt for secret values when a Blueprint is created. The
  `render.yaml` in this repository marks `DETOUR_DATABASE_URL` as asked-for and
  `DETOUR_TOKEN_SECRET` as generated; the Blueprint preview lists both before anything deploys.

## Where each secret lives

Secrets are never committed. Nothing in this repository is a secret.

| Value | Set in | Used by |
|---|---|---|
| Supabase database password | Supabase (you choose it), copied into the Render variable below | the database |
| `DETOUR_DATABASE_URL` | Render, service Environment tab | the API |
| `DETOUR_TOKEN_SECRET` | Render generates it (Environment tab) | the API; signs installation tokens |
| `DETOUR_API_URL` (repository variable) | GitHub, Settings, Secrets and variables, Actions, **Variables** | the APK build; it is a public address, not a secret |

Never paste the database password or the connection string into a chat, an issue or a commit.

---

## Step 1. Merge the Phase 1 work into `main`

Render's Blueprint in this repository deploys the `main` branch. The work is on the branch
`claude/affectionate-faraday-td3c57`. Open a pull request into `main` on GitHub (or ask your
assistant to) and merge it once the **CI** workflow is green.

**Check:** on GitHub the `main` branch shows the folders `apps`, `services`, `packages`, and the
file `render.yaml`.

## Step 2. Create the Supabase project

1. Go to <https://supabase.com> and sign up (the Free plan is enough).
2. Create a new organization if asked, then **New project**.
3. Name: `detour`. Region: pick **Central EU (Frankfurt)**, to match `region: frankfurt` in
   `render.yaml`. If you live elsewhere, change `region` in `render.yaml` first (it cannot be
   changed after Render creates the service) and pick the nearest matching Supabase region.
4. Database password: use **Generate a password**, then store it in a password manager. You will
   need it once, in step 4.
5. Create the project and wait until the dashboard finishes setting it up.

**Check:** the project dashboard opens. Supabase allows two active Free projects and pauses an
idle one after a week (ADR 005); this one is yours to keep active.

## Step 3. Enable PostGIS (confirms an open item)

1. In the project, open **Database**, then **Extensions**.
2. Search for `postgis` and switch it on. Accept the default schema `extensions`.

**Check:** `postgis` shows as enabled. If Supabase says it is not available on the Free plan, stop
and report that exact message: ADR 005 lists this as an unconfirmed risk. Phase 1 still works
without it.

## Step 4. Copy the connection string

1. Click **Connect** at the top of the project page.
2. Choose **Session pooler**. The string looks like
   `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-<n>-<region>.pooler.supabase.com:5432/postgres`.
3. Replace `[YOUR-PASSWORD]` with the password from step 2. If the password contains characters
   such as `@`, `:`, `/`, `?` or `#`, percent-encode them (for example `@` becomes `%40`), or
   generate a new password with letters and digits only.
4. Add `?sslmode=require` at the end.

Keep the finished string in your password manager. You will paste it into Render in step 5.

**Check:** the string starts with `postgresql://postgres.`, has port `5432`, and ends with
`?sslmode=require`. Do not use the "Direct connection" string (IPv6) or port `6543`
(transaction mode).

## Step 5. Create the Render service from the Blueprint

1. Go to <https://render.com> and sign up. Choose the free options. Connect your GitHub account
   when asked and allow access to the `Detour` repository.
2. In the Render dashboard click **New**, then **Blueprint**.
3. Select the `Detour` repository and the branch `main`. Render reads `render.yaml`.
4. Name the Blueprint `detour`. When Render asks for `DETOUR_DATABASE_URL`, paste the string from
   step 4. `DETOUR_TOKEN_SECRET` is generated for you.
5. Review the preview: one web service `detour-api`, plan **Free**, region Frankfurt. Click
   **Deploy Blueprint**.
6. Wait for the first deploy to finish (several minutes: it installs the Python packages).

**Check:** the service page shows the status **Live** and a URL such as
`https://detour-api.onrender.com`. Write the URL down; Render adds a suffix if the name was taken.
In the service **Logs** you should see `migrations: ok` followed by the JSON startup line.

## Step 6. Check the health endpoint

Open these in a browser (replace the address with yours):

1. `https://<your-service>.onrender.com/v1/health` shows
   `{"status":"ok","service":"detour-api","version":"0.1.0","release":"<commit>"}`.
2. `https://<your-service>.onrender.com/v1/health/ready` shows `"database":{"status":"ok","schemas":["app","geo"],...}`.
   `postgis` shows a version number if step 3 worked, and `null` if PostGIS is not enabled.
3. `https://<your-service>.onrender.com/v1/config` shows the OpenFreeMap style URL and three
   credit lines.

**Cold start:** after 15 idle minutes the first request takes about a minute and the browser just
waits. That is expected and accepted (ADR 005).

If `/v1/health` works but `/ready` says `unavailable`, see Troubleshooting.

## Step 7. Tell GitHub the backend address

1. On GitHub open the repository, **Settings**, **Secrets and variables**, **Actions**,
   the **Variables** tab.
2. **New repository variable**: name `DETOUR_API_URL`, value your Render URL with no trailing
   slash, for example `https://detour-api.onrender.com`.

(You can instead type the URL into the workflow's `api_url` box each time, step 8.)

## Step 8. Build the Android APK

1. On GitHub open **Actions**, choose the workflow **Android APK**, then **Run workflow** on the
   `main` branch. Leave `api_url` empty to use the variable from step 7.
2. Wait about 14 minutes for a green tick. The run page lists the **Artifacts**.

**Check:** the artifact `detour-android-apk` exists. The run summary lists `api_url=` with your
address.

This is a release-variant APK with the JavaScript bundled in, not an Expo development build,
because a development build needs a computer running a development server (ADR 008 addendum). It
is signed with the public debug key, which is fine for a personal test phone and must be replaced
before any build is kept for real use (ADR 008, ADR 010).

## Step 9. Install it and call the backend from the phone

1. On the phone, open the repository's Actions page in the browser, open the run, and download the
   artifact `detour-android-apk` (a zip). Or download it elsewhere and move it to the phone.
2. Open the zip in the **Files** app and extract `detour.apk`.
3. Tap `detour.apk`. Android asks to allow installs from this source: allow it, then **Install**.
   If Play Protect warns about an unknown app, choose **More details**, **Install anyway**.
4. Open **Detour**. At the top a yellow bar says "Connecting to the server…", and after a few
   seconds "Waking the server…" if Render was asleep.
5. Open the **Settings** tab.

**Check (the Phase 1 test):** Settings shows `Status: connected`, `Server: detour-api 0.1.0
(<commit>)` and an `Installation:` identifier. The **Map** tab shows the OpenFreeMap map, a line
`Style URL (from the backend): https://tiles.openfreemap.org/styles/liberty`, and the credit line
at the bottom left that collapses to an "i" button after about five seconds.

**Check the cold start:** leave the phone and Render alone for 20 minutes, then open the app. The
yellow bar should say "Waking the server…" and clear within about a minute.

To remove the app: long-press its icon, **Uninstall**.

---

## Importing a region (Phase 2)

This loads a country's places and the GeoNames gazetteer into the Supabase database, so that
search and trips have data. It runs in GitHub Actions; nothing is installed on your computer.
**Nothing is imported until you do this.** The first run is the first time the import meets a real
extract, so start with the smallest country and read the report before importing the others.

1. **Deploy the Phase 2 code.** Merge the work into `main` (Render redeploys and `start.sh` runs
   the new migrations; the log shows `migrations: ok`). The import workflow also runs the
   migrations itself, so this is not a prerequisite.
2. **Add the database secret.** On GitHub: repository **Settings**, **Secrets and variables**,
   **Actions**, **Secrets** tab, **New repository secret**: name `DETOUR_IMPORT_DATABASE_URL`, value
   the same **Session pooler** string as in step 4 (port `5432`, ending `?sslmode=require`). The
   workflow refuses port `6543`.
3. **Run the workflow.** **Actions**, **Import region**, **Run workflow** on `main` (the button
   appears only for workflows on the default branch). Region: `austria`. Leave "Import the GeoNames
   countries, currencies and cities first" ticked the first time.
4. **Read the result.** The run page shows the report: the six readiness gates of ADR 009 with
   their values, places kept per kind, objects excluded per class and reason, and the size of the
   `geo` data. The artifact `import-austria` has `report.json`, `report.md` and
   `review-sample.json` (ten kept and ten excluded objects for each reviewed class, ADR 011).
   Please read the review sample and tell the assistant whether the selection rule is right.
5. **Check the backend.** Open `https://<your-service>.onrender.com/v1/regions` (no token needed):
   the region shows `"status": "available"` if every gate passed, `"disabled"` if one failed. A
   disabled region has its data loaded but cannot be used for trips. Then check **Database** in
   the Supabase dashboard for the size (limit 500 MB; gate 6 allows 250 MB for all regions).
6. **Next regions.** Czechia and Hungary, then Italy; Japan stays last and will fail gate 5 until a
   display rule for non-Latin names exists (ADR 009).

**What can go wrong, and what to report** (copy the exact message):

| Message | Meaning |
|---|---|
| `Repository secret DETOUR_IMPORT_DATABASE_URL is not set` | Step 2 |
| `The import needs a session-mode connection` | The string uses port 6543; use the Session pooler on 5432 |
| `cities file line N: M columns, expected 19` or `countryInfo.txt ...` | The GeoNames file layout differs from what the importer expects (ADR 012: unverified); report it |
| `could not download ...` for the extract | Geofabrik refused or was unreachable (terms: `api-evaluation.md` 4.1). Do not retry in a loop |
| `report and database disagree` | The import found an inconsistency and rolled back; nothing was changed. Report it |
| `type "geometry" does not exist` | PostGIS is not enabled, or not on the search path (the code puts `public, extensions` on it); check step 3 |
| A warning that the coverage polygon was not loaded | Geofabrik's `.poly` file could not be fetched; the region's boundary stays unknown, nothing else is affected |
| A yellow warning that a gate failed | Expected for a small or thin region; the report says which |

The import takes the database's only write lock for the whole run (a second import waits). The
data it writes can be rebuilt by running it again; it never touches the `app` schema.

---

## Deploying photos (ADR 022)

The backend streams stored photos to the app, so it needs the same two Storage settings as the
"Resolve images" workflow. Render redeploys by itself when `main` changes.

1. **Merge to `main`.** Render builds (`pip install .` now installs Pillow), `start.sh` runs
   migration `0009`, and the log shows `migrations: ok`.
2. **Set two variables on the service.** Render dashboard, the `detour-api` service, **Environment**,
   **Add Environment Variable**: `DETOUR_SUPABASE_URL` (the project URL, `https://<project>.supabase.co`)
   and `DETOUR_SUPABASE_SERVICE_KEY` (the Supabase **secret** key, from Project Settings, API Keys).
   Saving restarts the service.
3. **Check.** `https://<your-service>.onrender.com/v1/images/<an id from geo.image>` answers with a
   JPEG (200); 503 means the two variables are missing or wrong, 404 an unknown or hidden image.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Render deploy fails during build | Python version or package error | Open the deploy log. `PYTHON_VERSION` is set in `render.yaml` to `3.13.5` |
| Log shows `ERROR migrations failed` | Wrong or unreachable `DETOUR_DATABASE_URL` | Re-copy the Session pooler string (step 4). The API keeps running so `/v1/health` still answers |
| `/v1/health/ready` says `unavailable` | Database unreachable, paused or wrong password | Supabase dashboard: unpause the project if paused; fix the variable in Render, Environment tab, then **Manual deploy** |
| `password authentication failed` in logs | Password mismatch or unencoded special character | Reset the database password in Supabase (Database settings), rebuild the string, update Render |
| App says "This build has no backend URL" | APK built without `DETOUR_API_URL` or `api_url` | Do steps 7 and 8 again |
| App stays on "Waking the server…" longer than 2 minutes | Render service suspended or crashed | Check the service status and logs in Render |
| After changing `DETOUR_TOKEN_SECRET`, the app shows a new installation | Old tokens no longer verify | Expected: the app registers again by itself |
| Map is grey but the backend is connected | Phone cannot reach `tiles.openfreemap.org` (for example a work network) | Try mobile data |

## Limits that matter

From the pages read on 2026-11-12 (ADR 005 has the full list). They can change; re-read before
relying on them:

- Render free: sleeps after 15 idle minutes, 750 instance hours a month, 512 MB RAM, restarts at
  any time, no persistent disk.
- Supabase Free: 500 MB database, paused after one week of inactivity, no automatic backups.
- GitHub Actions in a private repository: the APK build costs about 14 of the roughly 2,000
  monthly minutes.

## Not done in Phase 1

- A project-owned signing key for the APK (ADR 008). Until then each build is signed with the
  public debug key.
- Backups of the `app` schema, which is empty now (ADR 005, item 5).
- Notifying FOSSGIS (ADR 004): not needed; the owner decided on 2026-11-12 that the app is for the
  owner and one other person only (addendum to ADR 004).
