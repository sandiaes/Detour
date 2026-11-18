# ADR 035 — The iPhone without a Mac and without a paid account (GitHub build, SideStore)

- **Status:** **Proposed** on 2026-11-18 (owner decision of 2026-11-16: build the unsigned `.ipa` on
  GitHub's macOS runners and install it with SideStore and a free Apple ID; AltStore as fallback).
  **Nothing is built yet.** Step 1 (reading the sources) is done; this ADR stops for the owner's
  answers (section 1) before any build step.
- **Date:** 2026-11-18
- **Amends:** [`008`](008-no-app-stores.md) decision 3 (the iPhone is no longer built on the owner's
  Mac; see the note added there). Builds on [`034`](034-people-devices-and-shared-trips.md) (the
  partner joins by a code), [`007`](007-licence-apache-2.md) addendum (public
  repository), [`../ios-readiness.md`](../ios-readiness.md).
- **Related:** [`../privacy.md`](../privacy.md), [`../security.md`](../security.md),
  [`../android-release.md`](../android-release.md)

## 1. Read this first: what is different from what the owner was told, and the questions

**Facts that differ from the 2026-11-16 description** (all read on 2026-11-18, sources in section 3):

1. **SideStore's sign-in was broken by a change on Apple's side, and the fix is an "alpha".**
   SideStore's releases page titles 0.6.4 "DO NOT USE SIGN-IN IS BROKEN ON 0.6.4 AND BEFORE". The
   release marked *Latest* is **0.7.0-alpha** (15 Sep 2026, built from the same commit as the "Alpha"
   pre-release), labelled experimental, whose notes say Apple's server-side changes "broke 0.6.4 and
   prior versions" and that it "addresses the sign-in issue with 503 status code". No release on
   that page is marked stable. Yet SideStore's install guide still says "Select 'Install SideStore
   (Stable)'" in iloader, and its release-notes page stops at 0.6.2. **I could not establish which
   version "Stable" installs today or whether a new person can sign in with it.** This is the biggest
   risk to the plan: the route depends on a pre-release of a community tool.
2. **The Shortcuts action exists, but it is unreliable right now.** SideStore issues call it the
   "Refresh All Apps" shortcut. Open issues on 2026-11-18: #1723 (an automation fails with "device has
   not been unlocked recently" when the phone is locked; iOS 27.2), #1613 ("Refresh All Apps" fails,
   `targetAppBundle` missing), #1704 (action not found). Closed in September: "You are not signed in"
   (#1584) and ADI error -45061 (#1596, #1600). SideStore's docs say it "will periodically 'refresh'
   your apps in the background" and its site says "no computer after the initial install, only a
   Wi-Fi connection", but the docs do **not** describe a Shortcuts action or an automation. So
   "automatic daily renewal without opening the phone" is **not confirmed**; the guide must also teach
   a manual refresh, and the owner or partner should expect to open SideStore now and then.
3. **A computer is needed again when the pairing file lapses.** SideStore: the pairing file "may
   expire and need to be reimported if you update or reset your iPhone ... This also occurs at random
   times", fixed with iloader on a PC. So the PC is not needed *only once*.
4. **The 10 App IDs limit.** Apple's page says "up to 10 App IDs, which expire after 7 days"; it does
   not say "a week" as a rolling per-week rule. SideStore's FAQ says "only 10 different apps may be
   installed in a week". Detour (no extensions) uses one App ID, SideStore uses its own.
5. **Apple's 3-app limit includes SideStore** (SideStore's FAQ: "3 apps (including itself)"), so
   Detour plus SideStore leaves one slot.
6. **Not verified** (the sources did not say, or could not be read): which capabilities a free account
   lacks, row by row (Apple's table lost its marks when read; Detour needs none, see decision 2);
   whether SideStore appends the team id to the bundle identifier; whether the keychain item and the
   app's files survive an install-over or a lapse (Expo says the secure-store item "will persist
   across app uninstallations when the app is reinstalled with the same bundle ID" and that this "is
   not guaranteed"; nothing on re-signing); SideStore's default anisette server and what it sends;
   the minutes one macOS build takes; the maximum artifact retention; MapLibre React Native's minimum
   iOS version; whether `pillow-heif`'s wheels carry only permissive code (decision 5); AltStore's
   own app slot. Each is turned into a check on a device or in the first workflow run (section 8).

**Questions for the owner** (my recommendation first):

| # | Question | Recommendation |
|---|---|---|
| Q1 | Given fact 1, go ahead with SideStore, or (a) wait until SideStore has a stable release that signs in, (b) use AltStore classic from the start, (c) pay for the Apple Developer Program ($99 a year; TestFlight, 1 year, no PC)? | Go ahead and build the `.ipa` (it works with any of these), but **install with SideStore only after trying its current build on the partner's phone**; if sign-in fails, use AltStore (decision 8). Paying stays the clean exit if the free route is too fragile. |
| Q2 | Which Apple ID: the partner's own, or a new free one made only for signing? | **A separate free Apple ID** (decision 6). |
| Q3 | Photos: is the Files-app picker enough, or add a photo picker (`expo-image-picker`, MIT, adds the photo-library usage string)? | Add it (decision 5). A cover from the camera roll is the normal iPhone use. |
| Q4 | HEIC: convert on the phone, or decode on the server? | On the phone, with `expo-image-manipulator` (MIT). |
| Q5 | iCloud backup of the app's files: exclude documents and covers (as on Android), or leave them in the backup? | Exclude them (decision 3), because the server now keeps the shared copies and the trip file is the backup. |
| Q6 | Bundle identifier `io.github.sandiaes.detour`, version `0.2.0`, build number `1`? | Yes. |
| Q7 | May the build workflow be started from the app's GitHub repository by the owner only (default for `workflow_dispatch`)? | Yes. |

## 2. Context

ADR 008 decision 3 assumed an Xcode build on the owner's Mac. The owner has no Mac, will not pay for
the Apple Developer Program, and the second person who needs the app (ADR 034) has an iPhone. The
repository is public (ADR 007 addendum), so GitHub's standard macOS runners cost nothing. A
free-account app is signed for 7 days; SideStore re-signs on the phone.

## 3. What the sources say (read 2026-11-18)

| # | Fact | Source |
|---|---|---|
| A1 | A free account's provisioning profile "will expire 7 days from issuance. You'll need to rebuild and reinstall your app to your device after expiration." "You can install up to 3 apps per device." "You can register up to 10 App IDs, which expire after 7 days." | <https://developer.apple.com/support/compare-memberships/> |
| A2 | Developer Mode: "turn on the Developer Mode switch under Security" in Privacy & Security; a restart and a confirmation with the passcode follow; it "only appears in Settings if you initiate pairing or if you previously paired the device to a Mac". | <https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device.md> |
| A3 | Capabilities have an "Apple Developer" (free) column; the marks per row could not be read. Detour needs no capability: no push, no iCloud, no associated domains, no App Groups. | <https://developer.apple.com/help/account/reference/supported-capabilities-ios> |
| G1 | "The use of standard GitHub-hosted runners is free ... In public repositories". | <https://docs.github.com/en/billing/managing-billing-for-your-products/about-billing-for-github-actions> |
| G2 | `macos-latest` = `macos-26` (arm64, macOS 26.7.2); default Xcode 26.6, also 26.5, 26.4.1, 26.3 ... `macos-15` has Xcode 26.3 as its newest. "All macOS 14 images retired from GitHub Actions on November 2, 2026." Larger runners (`-large`, `-xlarge`) are billed even for public repositories. | <https://github.com/actions/runner-images> and its `images/macos/macos-26-arm64-Readme.md`, `macos-15-arm64-Readme.md` |
| G3 | "Each job in a workflow can run for up to 6 hours". | <https://docs.github.com/en/actions/reference/limits> |
| E1 | Expo SDK 58: React Native 0.88, React 19.3, iOS 16.4+, **Xcode 26.4+**, Node 22.13+. | <https://docs.expo.dev/versions/latest/> |
| E2 | `expo prebuild --platform ios` "creates the ... ios directories"; `--no-install` skips installs; `--clean` deletes existing native directories. `ios.bundleIdentifier`, `ios.buildNumber` ("Corresponds to `CFBundleVersion`"), `ios.infoPlist` ("arbitrary configuration to add to ... Info.plist"). | <https://docs.expo.dev/workflow/continuous-native-generation.md>, <https://docs.expo.dev/versions/latest/config/app.md> |
| E3 | Secure store on iOS: item accessible `WHEN_UNLOCKED` by default; "data stored with `expo-secure-store` will persist across app uninstallations when the app is reinstalled with the same bundle ID ... this is not guaranteed". | <https://docs.expo.dev/versions/latest/sdk/securestore/> |
| E4 | `expo-image-picker`: "No permissions request is necessary for launching the image library"; the config plugin adds `NSPhotoLibraryUsageDescription` (and camera and microphone strings unless set `false`). A HEIC original can be returned. `expo-image-manipulator` supports iOS and Android. Both are MIT (npm, 58.0.10 and 58.0.16). | <https://docs.expo.dev/versions/latest/sdk/imagepicker.md>, <https://docs.expo.dev/versions/latest/sdk/imagemanipulator.md> |
| M1 | MapLibre React Native 11: wraps MapLibre Native iOS 6.31.0 and Android 13.6.1; React Native ≥ 0.80; "From v11 onwards only the new architecture is supported". No minimum iOS version stated. | <https://maplibre.org/maplibre-react-native/docs/setup/getting-started> |
| S1 | SideStore needs "iOS/iPadOS 15.0 or higher", a passcode, a Windows 8 or higher PC (64-bit; "Windows 10 on Arm" not supported) **only for the first install**, an Apple Account, Wi-Fi ("mobile network is not suitable"). | <https://docs.sidestore.io/docs/installation/prerequisites> |
| S2 | Windows: install **iTunes "from the Microsoft Store or directly from Apple"** ("recommended to use the version ... directly from Apple"), then **iloader** (MSI recommended). | same page |
| S3 | On the phone: install **LocalDevVPN** "from the Apple App Store or from the AltStore PAL source" and connect it; "required to be turned on any time you wish to install, update, or refresh apps in SideStore". LocalDevVPN: "All traffic stays on-device with no data collection or external connections". | same page; <https://github.com/jkcoxson/LocalDevVPN> |
| S4 | Install: iloader on the PC, sign in with the Apple Account ("doesn't need to be the account associated with the device"), "Install SideStore (Stable)"; then trust the developer app (Settings, General, VPN & Device Management), turn on Developer Mode, open LocalDevVPN, sign in to SideStore, tap the "7 DAYS" counter in My Apps to refresh SideStore first. | <https://docs.sidestore.io/docs/installation/install> |
| S5 | Pairing file: "may expire ... if you update or reset your iPhone ... also at random times"; replaced with iloader ("Delete Stored Pairing", "Manage Pairing File", "Place"). | <https://docs.sidestore.io/docs/advanced/pairing-file> |
| S6 | Anisette: "information used in the app signing process" that "needs to be generated each time you install or refresh apps"; SideStore gets it from a server; "No account info is sent to the server ever". Old shared v1 servers locked accounts, "This is why we recommended using a separate burner Apple Account". Fake Macs appearing in the Apple ID's device list are "automatically generated by the Anisette server". 0.6.4 notes: on-device anisette is the primary source for 2FA. | <https://docs.sidestore.io/docs/advanced/anisette>, <https://docs.sidestore.io/docs/faq>, releases page |
| S7 | "SideStore will periodically 'refresh' your apps in the background, to keep their normal 7-day development period from expiring." Free account: "3 apps (including itself)", "10 different apps ... in a week". | <https://docs.sidestore.io/docs/faq> |
| S8 | Install any `.ipa` (site: "Install any .ipa"; docs: "install your IPA as usual"). "Sideload the same or an updated IPA ... with your data still intact" (for apps moved from AltStore); a nightly SideStore installed over "your data should remain". Nothing says an unsigned `.ipa` is accepted, or about the keychain. | <https://sidestore.io/>, FAQ |
| S9 | Releases: Latest 0.7.0-alpha (2026-09-15, experimental); 0.6.4 "DO NOT USE SIGN-IN IS BROKEN ON 0.6.4 AND BEFORE"; 0.6.3 "Please reinstall with iloader" for iOS 26.4+ VPN errors. | <https://github.com/SideStore/SideStore/releases> |
| S10 | Shortcut issues (#1723, #1613, #1704, #1584, #1596, #1600) quoted in section 1. | <https://github.com/SideStore/SideStore/issues?q=shortcut+refresh> |
| S11 | iloader 2.4.1: "Install SideStore ... import certificate and place ... pairing files automatically", "Import any IPA"; "Do not download from any other sources" than iloader.app or its GitHub repository; Windows needs iTunes. | <https://github.com/nab138/iloader> |
| T1 | AltStore classic on Windows: iTunes and iCloud "directly from Apple (not the Microsoft Store)", AltServer, enable Wi-Fi sync in iTunes; "Your Apple ID and password are sent only to Apple". AltStore "will try to automatically refresh your apps throughout the week", so leave AltServer running; "up to 10 App IDs at a time, but each App ID expires after one week". The PC must be on the same Wi-Fi. | <https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows>, `/altserver`, `/app-ids` |

## 4. Decision

1. **The build** (built after approval): workflow `.github/workflows/ios-ipa.yml`, by hand only
   (`workflow_dispatch`, input `api_url`, variable `DETOUR_API_URL`, like "Android APK"). Runner
   `macos-26` (Xcode 26.6 is the default; Expo SDK 58 needs 26.4 or later, so `macos-15` cannot
   build it). Steps: Node 22, `npm ci`, type check, `expo prebuild --platform ios --no-install
   --clean`, `pod install`, `xcodebuild archive` for `generic/platform=iOS`, Release, with
   `CODE_SIGNING_ALLOWED=NO` (Expo's docs do not describe this step; the first run proves it), then
   `Payload/Detour.app` zipped as `Detour.ipa`. Uploads `Detour.ipa` and `build-info.txt` (commit,
   API URL, size, SHA-256, bundle id, version, build number, minimum iOS) with 14 days' retention. The
   job has `permissions: contents: read`, no secrets, no Apple credentials or certificates. The log
   and summary carry no personal or secret value.
2. **`app.json` `ios` block:** `bundleIdentifier: io.github.sandiaes.detour` (SideStore may rewrite it
   with the team id; if so, `.detour` handling and the keychain item must be checked, section 8),
   `buildNumber`, `icon` (1024 px, from `assets/icon.png` after checking its size), `supportsTablet:
   false`, `infoPlist`: `ITSAppUsesNonExemptEncryption: false` (HTTPS only), `UIFileSharingEnabled:
   false`, `LSSupportsOpeningDocumentsInPlace: false`, `CFBundleDocumentTypes` and
   `UTExportedTypeDeclarations` for `.detour` (identifier `io.github.sandiaes.detour.trip`, conforms
   to `public.zip-archive`; role Viewer; "Open in place" off, so the import gets a copy). **No usage
   strings** for location, camera, microphone or contacts; `NSPhotoLibraryUsageDescription` only if Q3
   is yes (one honest sentence). Capabilities: none. `plugins/permissions.test.js` gains an `ios`
   part: no location, camera, microphone, tracking or Bluetooth string; the `.detour` type is
   declared; no background mode; no push entitlement.
3. **Backups:** iOS backs up an app's `Documents` and `Library` (not `Caches` or `tmp`) to iCloud and
   to a computer by default. Android has `allowBackup: false`. Equivalent chosen (Q5): the app marks
   its documents, covers and SQLite cache folders **excluded from backup** (`isExcludedFromBackup`
   through an Expo config plugin or `expo-file-system` if its API offers it; to be verified at build
   time, otherwise store them under `Library/Caches`-like locations the app already can recreate).
   The keychain token is not in the file backup. Reason: shared documents and covers are on the server
   (ADR 034), the trips are on the server, and a restored copy of private documents in iCloud is a
   second, unlisted place for them. Recorded in `privacy.md` and `security.md` after approval.
4. **The secure token:** `expo-secure-store` keeps it in the keychain, accessible when unlocked. Whether
   the keychain item survives SideStore's re-sign (same Apple ID, same bundle id) and an install-over
   is **not documented**, so it is checked on a phone (section 8). The app already treats an unreadable
   token as none and registers again, which makes the person a new, empty one. **The guide says so**:
   the person's trips are on the server; they come back with the **recovery code** or a **link code
   from another phone** (ADR 034). Therefore the guide has the partner write down the recovery code
   (More, Your phones) before anything else is done.
5. **Pictures:** `File.pickFileAsync` opens the Files app on iOS, not the photo library. Camera-roll
   pictures are HEIC by default, so: **add `expo-image-picker`** (MIT) for covers only, and convert to
   **JPEG on the phone** with `expo-image-manipulator` (MIT) before upload (longest side 1600 px, no
   EXIF as the server also strips it). Reasons: the server's cover step (`repo/trip_files.py`,
   Pillow 12.3.0) accepts JPEG, PNG and WebP and refuses HEIC; decoding HEIC on the server needs
   `pillow-heif` (BSD-3-Clause per PyPI, 2026-11-18) which wraps libheif and codecs whose licences I
   could not read (its documentation host was blocked), so by CLAUDE.md I do not add it; the phone
   converts with the operating system's own decoder at no licence cost; and the server keeps one
   rule. Documents keep accepting HEIC as uploaded (decided in ADR 034). The photo-library string is
   the only new permission text.
6. **Which Apple ID:** a **separate free Apple ID made only for signing**, not the partner's own.
   Reasons, in plain words: SideStore signs in to Apple with it from the phone and from iloader, Apple
   will list "Macs" (made by the anisette server) in its devices, a mistake or Apple's security can
   lock it, and a lock on the partner's main Apple ID would cost them iCloud, messages and photos.
   SideStore's own docs recommend a "burner" account for this reason. It needs a separate email
   address and two-factor authentication on a phone number. The cost is one more account to keep.
7. **Not covered:** no App Store, no TestFlight, no push notifications, no widgets, no background
   fetch. If the 7 days run out without a renewal, Detour will not open until it is refreshed from
   SideStore (if SideStore itself is still valid) or reinstalled from the PC. Shared trips stay safe
   on the server; the phone's offline copy is only a copy.
8. **Fallback:** AltStore classic with AltServer on the owner's Windows PC over home Wi-Fi (T1): the
   same `.ipa`, a PC that must be on and on the same Wi-Fi for each refresh, iTunes and iCloud from
   Apple's site. The guide keeps it brief.

## 5. Alternatives

| Alternative | Why not (now) |
|---|---|
| Apple Developer Program ($99/year) and TestFlight | The owner declined; kept as the clean exit if the free route fails (Q1). |
| Web version (PWA) | Set aside by the owner: weeks of work and weaker offline. |
| Expo Go | Cannot load MapLibre. |
| EU alternative marketplaces | Still need a paid account (owner). |
| EAS Build in the cloud | Needs credentials or a paid account for device installs; would put Apple credentials with a third party. |
| Sideloadly, or others | Not requested; same Apple limits; not read. |
| Decode HEIC on the server | Licence unclear (decision 5); one more dependency in the API. |

## 6. Consequences

- The owner needs no Mac; the PC is needed for the first install, for a lapsed pairing file and for the
  AltStore fallback.
- The iPhone route depends on three community tools (SideStore, iloader, LocalDevVPN) and on Apple not
  changing its sign-in again; the guide says so (known limits).
- Two new Expo dependencies (both MIT, both iOS and Android); the Android APK grows slightly. KPI
  "Android-only native dependencies: 0" stays met.
- A version of the app on the phone stops working after 7 days unless refreshed.
- ADR 008 decision 3 is superseded for the iPhone; ADR 008 gets a one-line amendment note.

## 7. Build order after approval

1. `ios` block, config plugin if needed, `permissions.test.js` iOS part.
2. HEIC on the phone (and the photo picker if Q3), tests with a HEIC fixture and a JPEG-with-EXIF case.
3. iOS pass over `apps/mobile/src` (safe areas, keyboard, `.detour` opening through `Linking`,
   `expo-sharing`, document opening, the MapLibre attribution line), with a test that renders with
   `Platform.OS = "ios"`.
4. `ios-ipa.yml` (the owner starts it; fixes from the logs).
5. Version `0.2.0`, `ios.buildNumber` 1.
6. `docs/ios-install.md` (the owner's guide, written only against section 3's verified facts) and the
   document updates listed in the task.

## 8. To check on an iPhone (nothing was checked on one)

Which SideStore version installs and signs in; whether `Detour.ipa` unsigned installs; the bundle id
after signing; whether the keychain token and SQLite data survive a refresh and an install-over;
whether the Shortcuts "Refresh All Apps" automation runs with the phone locked; the first workflow
run's minutes and the `xcodebuild` flags; `.detour` opening from Files and the share sheet; safe
areas and the keyboard; the map attribution line.
