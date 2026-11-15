# Android release APK: build, install, update

Detour is not in any app store (ADR 008). The APK is built in GitHub Actions and installed by hand on
the owner's phone (a Samsung Galaxy S22 with Android 16 in the spike). Nothing is installed on a
computer. Written in Phase 9 (2026-11-15); the first-time backend setup is in
[`deployment.md`](deployment.md) steps 1 to 7.

## 1. Before the first build (once)

1. The backend is deployed on Render and `https://<your-service>.onrender.com/v1/health` answers
   (deployment steps 1 to 6).
2. GitHub, the repository, Settings, Secrets and variables, Actions, **Variables** tab: the variable
   `DETOUR_API_URL` holds the Render address with no trailing slash (deployment step 7).
3. Optional but recommended for real use: your own signing key (section 5). Without it the APK is
   signed with the public debug key, as every build so far.

## 2. Build the APK

1. GitHub, the repository, **Actions**, workflow **Android APK**, **Run workflow**.
2. Branch: `main` (or the branch you want to try). Leave `api_url` empty to use the variable.
3. Wait for the green tick: about 14 minutes.
4. Open the run. The summary shows `commit=`, `api_url=` (check it is your Render address),
   `apk_sha256=` and the signer certificate. Under **Artifacts** is `detour-android-apk`
   (kept 14 days).

**If the run fails within seconds with no log**, the jobs were not started: usually the month's
Actions minutes of the private repository are used up (about 2,000, ADR 005) or a spending limit
blocks them. Check Settings, Billing and plans, Usage. This happened on 2026-11-15 (audit).

## 3. Install it (first time)

1. On the phone, open the run's page in the browser (signed in to GitHub) and tap
   `detour-android-apk` under Artifacts. It downloads a zip.
2. Open the zip in the **Files** app (My Files on Samsung) and extract `detour.apk`.
3. Tap `detour.apk`. Android asks to allow installs from this source (the browser or Files): allow it,
   go back, tap **Install**. If Play Protect warns about an unknown app: **More details**,
   **Install anyway**.
4. Open Detour. A yellow "Connecting" notice, then "Waking the server" if Render was asleep (about a
   minute after 15 idle minutes). It now retries by itself if the first try fails.
5. More, **Settings**: `Status: connected`, the server version and commit, and an **Installation**
   identifier. Write the identifier down (it is needed to find your data on the server).

## 4. Update by hand

1. Build a new APK (section 2) from the commit you want.
2. Download and extract it as in section 3, tap it, and choose **Update** (Android calls it
   "Install" on some phones). **Do not uninstall first**: an update keeps the token, the saved trips
   and the documents.
3. Open Detour and check More, Settings shows the new commit.

An update installs over the old app **only if both are signed with the same key**. If Android says
"App not installed" or "conflicts with an existing package", the keys differ: see section 5.

## 5. Your own signing key

The public debug key is the same for every React Native developer, so anyone could sign an "update"
that installs over Detour (ADR 008, [`security.md`](security.md)). Moving to your own key:

1. **Before anything else: More, Back up all trips, with documents**, and save the file off the phone.
   Switching keys needs one uninstall, which deletes the documents and the installation token.
2. Actions, **Create signing key**, Run workflow, type `CREATE`. Run it **once**: a second run makes a
   different key.
3. Open the run, download the artifact `signing-key` (kept one day). Unzip it on any computer or the
   phone.
4. Repository Settings, Secrets and variables, Actions, **Secrets**: create four secrets and paste the
   contents of the file of the same name: `DETOUR_KEYSTORE_BASE64`, `DETOUR_KEYSTORE_PASSWORD`,
   `DETOUR_KEY_ALIAS`, `DETOUR_KEY_PASSWORD`.
5. Keep `detour-release.keystore` and the password in your password manager. Losing them means
   every later build needs another uninstall.
6. Delete the "Create signing key" run (its page, the three dots, Delete workflow run).
7. Build the APK (section 2). The summary now shows your certificate, not "Android Debug".
8. On the phone: uninstall Detour, install the new APK, open it (it registers a new installation),
   then **More, Import a trip** and choose the backup file. Your trips come back as new copies with
   their documents (ADR 028). The old installation's data stays on the server; delete it with the SQL
   in [`privacy.md`](privacy.md), section 5, once the import looks right.

Do this when you have a quiet moment, not during a trip.

## 6. Checking an APK you downloaded

The run summary lists `apk_sha256`. On the phone it is not easy to compute; what matters is that the
file came from this repository's own Actions run. Never install a Detour APK from anywhere else.

## 7. Removing the app

Long-press the icon, **Uninstall**. This deletes the documents and the saved copies on the phone
([`privacy.md`](privacy.md)); export first if you want to keep them.
