# Prompt: the iPhone build without a paid Apple account (GitHub build + SideStore)

Paste everything below the line into a new Claude Code session on this repository.

---

You are working on Detour (read `CLAUDE.md` first and follow it exactly). Your task is **design first, then
build**: make the app installable on an iPhone **without a Mac and without the paid Apple Developer Program**,
and write a step-by-step guide the owner can follow on their Windows PC and on the iPhone. The iPhone belongs
to the owner's partner, who will use Detour with the owner through the shared trips of ADR 034.

## Why and what the owner decided (2026-11-16)

- ADR 008 decision 3 says the iPhone app is built on the owner's Mac with Xcode. **The owner has no Mac**
  and does **not** want to pay for the Apple Developer Program.
- The owner chose: **build the iPhone app file (`.ipa`, unsigned) on GitHub Actions' macOS runners** (the
  repository is public, ADR 007 addendum), then **install it with SideStore and a free Apple ID**. SideStore
  re-signs the app on the iPhone itself, so the 7-day expiry of a free-account app can be renewed without a
  computer, and an **iOS Shortcuts automation** renews it automatically (for example daily). AltStore over
  home Wi-Fi is the fallback.
- A web version (Safari, Add to Home Screen) was considered and set aside: weeks of work and weaker offline.
- Expo Go cannot run Detour (MapLibre is not in it). EU alternative marketplaces still need a paid account.

Everything above about Apple's and SideStore's rules was said **from memory**. Verify it first (step 1).

## Step 1: read and verify (record each fact with its link and the date read)

Re-read the official pages; do not copy figures from memory or third-party lists (CLAUDE.md):

1. **Apple, free provisioning with a personal Apple ID**: how long a signed app stays valid (7 days?),
   how many sideloaded apps per device (3?), how many App IDs per week (10?), which capabilities are not
   allowed, and Developer Mode on iOS 16 and later.
2. **GitHub Actions macOS runners**: that standard runners are free for public repositories, the current
   image names and their Xcode versions, and the timeout. Record the minutes one build takes.
3. **Expo SDK 58 / React Native 0.88**: the minimum Xcode and iOS deployment target; how `expo prebuild
   --platform ios`, CocoaPods and an `xcodebuild archive` with signing turned off fit together; whether
   MapLibre React Native 11.5.1 needs anything on iOS.
4. **SideStore's own documentation** (its site and GitHub): the current install method from **Windows**
   (which installer it recommends now, e.g. iloader or another; iTunes and iCloud from Apple's site rather
   than the Microsoft Store, if still required), the **pairing file**, the **on-device VPN app** it needs
   (name as of today), the anisette server and what it sends, how "Refresh All" works, whether it offers
   a **Shortcuts action** for refreshing, how many app slots SideStore itself uses, and what happens to an
   installed app's data when a newer `.ipa` is installed over it or when it lapses.
5. **AltStore classic** from Windows (AltServer), as the fallback: background refresh over the same Wi-Fi.

If a fact turns out different from what the owner was told (for example SideStore can no longer refresh on
the phone, or the limits changed), stop and tell the owner before building.

## Step 2: write ADR 035 (status Proposed) and stop for the owner

`docs/decisions/035-iphone-without-a-paid-account.md`, in the format of ADR 029 to 034: context, decision,
alternatives, consequences, and the verified facts with links and dates. It **amends ADR 008 decision 3**
(add an amendment note there; do not rewrite it). It must decide and explain:

1. **The build**: a workflow `.github/workflows/ios-ipa.yml`, run by hand like "Android APK", with the
   same `api_url` input and `DETOUR_API_URL` variable; it uploads an unsigned `Detour.ipa` plus a
   build-info file. **No Apple credentials, certificates or secrets in GitHub**: SideStore signs on the
   phone. Nothing personal or secret may be logged (the repository is public).
2. **The `ios` block in `app.json`**: `bundleIdentifier` (e.g. `io.github.sandiaes.detour`; note that
   SideStore may append the team id), the icon, a document type and exported type for `.detour` so the
   import from Files and the share sheet work (Info.plist through config, no hand-edited native project),
   no permission strings the app does not need, and an `ios` part of `plugins/permissions.test.js`.
3. **Backups**: Android has `allowBackup: false`. Decide the iOS equivalent for the documents, covers and
   SQLite cache (iCloud backs up the app's files by default), and record it in `docs/privacy.md` and
   `docs/security.md`.
4. **The secure token**: `expo-secure-store` keeps the device token in the keychain. Check whether a
   re-sign by SideStore (same Apple ID) or installing a newer build keeps it. If it can be lost, the
   person keeps their trips through ADR 034's recovery code or a link code from the owner's phone: say so
   in the guide.
5. **Pictures on iPhone**: covers and documents are picked with `File.pickFileAsync` from `expo-file-system`
   (`apps/mobile/src/documents/files.ts`), which opens the Files app on iOS, not the photo library. Decide
   whether that is enough or a photo picker is needed (a new dependency and a photo-library usage string;
   ask the owner). **HEIC**: iPhone pictures are usually HEIC and the server's cover step (Pillow,
   `repo/trip_files.py`) refuses them. Choose: convert to JPEG on the phone before upload, or decode HEIC on
   the server. Check each option's licence (CLAUDE.md, ADR 007) and record why. Documents already accept HEIC
   as uploaded.
6. **Which Apple ID**: the partner's own, or a separate free Apple ID made only for signing (SideStore sends
   it to Apple and an anisette server). Recommend one and say why, in plain words, in the guide.
7. **What is not covered**: no App Store, no TestFlight, no push notifications; the app stops opening if the
   7 days run out without a renewal until it is reinstalled from the PC.

This is a new distribution route with a third-party tool, so **stop after the ADR and its open questions and
wait for the owner's answers**. If questions cannot be asked interactively, put them at the top of the ADR.

## Step 3: after approval, build in small steps, each with tests

1. `app.json` `ios` block and any Expo config plugin needed (never edit a native project; CLAUDE.md), with
   tests like the Android plugin tests.
2. The HEIC decision (phone or server), with tests (a HEIC fixture; a JPEG with EXIF still stripped).
3. An iOS pass over `apps/mobile/src`: safe areas and the notch on every screen, the keyboard over forms
   (`KeyboardAvoidingView` behaviour differs on iOS), the `.detour` file opening through
   `Linking.getInitialURL` and `url` events in `src/App.tsx`, `expo-sharing` for export, opening documents,
   the MapLibre attribution line. Today there is no `Platform.OS` branch; add one only where iOS truly needs
   it, with a test that renders with the iOS platform.
4. The `ios-ipa.yml` workflow: `macos-*` runner, Node 22, `npm ci`, type check, `npx expo prebuild --platform
   ios --no-install --clean`, `pod install`, `xcodebuild archive` (Release, `generic/platform=iOS`, signing
   off), then `Payload/Detour.app` zipped into `Detour.ipa`; a step summary with commit, API URL, size,
   SHA-256, bundle id, version and minimum iOS; artifact retention 14 days. Validate the YAML in CI if the
   repository does that for other workflows. You cannot run it from the session unless the owner starts it;
   ask them to, and fix what fails from the logs.
5. Bump `expo.version` and set `ios.buildNumber` so an update installs over the old app.

## Step 4: the owner's guide, `docs/ios-install.md`

Plain words, numbered steps, one action per step, what the owner should see after each. Every step must match
what step 1 verified (link the official page beside the step). Sections:

A. **Build the app file**: Actions, "iOS IPA", Run workflow, wait, download the artifact, unzip to get
   `Detour.ipa`, copy it to the iPhone (Files app, via iCloud Drive, a cable or AirDrop from another Apple
   device).
B. **Prepare the Windows PC once**: what to install and from where (exactly as SideStore's docs say today).
C. **Prepare the iPhone once**: turn on Developer Mode, install SideStore with the PC, trust what must be
   trusted, add the pairing file, install and turn on the VPN app it needs, sign in to SideStore with the
   chosen Apple ID.
D. **Install Detour**: in SideStore, add `Detour.ipa`; open Detour; it connects to the server.
E. **Join the owner's account or trips** (ADR 034): the owner makes an invite code in More, People; the
   partner enters it. Or, for the owner's own iPhone, a link code from More, Your phones. Show where each
   screen is.
F. **Automatic renewal**: a Shortcuts personal automation (time of day, daily, run without asking if iOS
   allows) that runs SideStore's refresh; how to check the expiry date in SideStore; what notifications
   to expect.
G. **Before a trip**: refresh by hand, check that the expiry is after the trip ends; download-ahead of shared
   documents (trips within 14 days) needs Detour opened once with signal.
H. **Updating Detour**: run the workflow again, install the new `.ipa` over the old one in SideStore; what
   is kept (data, token) as verified.
I. **If it stopped opening**: reconnect to the PC and reinstall SideStore, then Detour; the trips are on the
   server; if the phone's sign-in was lost, use the recovery code or a link code.
J. **Fallback, AltStore with home Wi-Fi**, briefly.
K. **Known limits**: the free-account limits as verified, what Apple changes can break, and that nothing
   was checked on an iPhone by Claude.

## Step 5: documents and checks

- Update in the same change: `CLAUDE.md` (Current state), `docs/ios-readiness.md` (the Mac route becomes
  the GitHub + SideStore route; keep section 4's checklist and add to it), ADR 008 amendment note,
  `docs/app-plan.md` (Phase 11), `docs/known-limitations.md`, `docs/privacy.md`, `docs/security.md`,
  `docs/development.md` (the new workflow), `docs/build-prompts.md` Prompt 13, `docs/test-plan-phase-9.md`
  (iPhone journeys: install, join with a code, a shared trip, a shared document, export and import, renewal).
- Run `npm run format:check`, `typecheck`, `lint`, `npm test`, and in `services/api` `ruff check`,
  `ruff format --check`, `mypy`, `pytest` if the backend changed. Report results as they are, and say plainly
  that nothing was installed on an iPhone.
- Work on the session's branch, commit in clear steps and push. Do not open a pull request unless asked.
