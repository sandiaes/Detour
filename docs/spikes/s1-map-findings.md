# Spike S1 — Map in an Android build made in GitHub Actions: findings

- **Date:** 2026-11-12
- **Question:** does MapLibre React Native render an OpenFreeMap style in an Expo build on
  Android, and can the Android APK be built in GitHub Actions without Android Studio on any local
  machine (ADR 008)?
- **Code (throwaway):** `spikes/s1-map/` (one-screen Expo app) and
  `.github/workflows/spike-s1-map.yml` (the APK build). Not product code; Phase 1 starts again.
- **Verification marks:** ✅ read on the official page on 2026-11-12; ◐ partly read; ✗ not read.

## 1. Result

**The APK builds in GitHub Actions with no local machine and no Android Studio.** First attempt,
run 1 of workflow "Spike S1 map APK" (run 43213779230, commit `ec6201c`, 2026-11-12), conclusion
success:

| Item | Result |
|---|---|
| Whole job | 13 min 41 s (821 s), on a GitHub-hosted `ubuntu-24.04` runner of this private repository |
| Gradle `assembleRelease` | 12 min 59 s, 331 tasks, `BUILD SUCCESSFUL` |
| `npm ci`, type check, `expo prebuild` | 14 s, 3 s, 1 s |
| APK | 32,853,767 bytes (31.3 MB), SHA-256 `98d44ee1…0220182`; artifact zip 13.7 MB |
| Package | `detour.spike.s1map`, version 0.1.0 (code 1), compileSdk 37, targetSdk 36, native code `arm64-v8a` only |
| Signature | APK Signature Scheme v2, `CN=Android Debug`, certificate SHA-256 `fac61745…91033b9c` (see Signing) |
| Cost | about 14 runner minutes, about $0.08 at $0.006 per minute, drawn from the $12 monthly allowance (section 7) |

**The map renders on a real phone (confirmed by the owner, 2026-11-12).** The owner installed the
APK from run 43213779230 by the steps in section 3 on a **Samsung Galaxy S22 with Android 16**.
The map appeared, and the status box read: `Detour spike S1`, `Map: loaded`,
`Config: bundled stand-in (spike-s1-2026-11-12)`, `From: spike-config.json`, and the Liberty style
URL. So MapLibre React Native 11.5.1 renders the OpenFreeMap style in our own build, with the
style URL taken from the config object. The owner did not report on the attribution line or the
"i" button; that check is still open (section 8).

Nothing on this path needs an Expo account, Expo's servers or Android Studio. Expo's cloud build
(section 6) is therefore not needed.

## 2. What was built

| Item | Value |
|---|---|
| Expo SDK | 58 (`expo` 58.0.24), React Native 0.88.1, React 19.3.0, versions taken from the `bundledNativeModules.json` shipped inside `expo` 58.0.24 |
| Map library | `@maplibre/maplibre-react-native` 11.5.1 with its Expo config plugin; component `Map`, style passed as `mapStyle` |
| Native project | Generated in the workflow by `npx expo prebuild --platform android --clean` (Continuous Native Generation); nothing native is committed or hand-edited |
| Build | `./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a` on a GitHub-hosted `ubuntu-24.04` runner, JDK 17 |
| Output | `detour-s1-map.apk` plus `build-info.txt` (sizes, SDK levels, signing certificate) in the artifact `detour-s1-map-apk`, kept 14 days |
| Style | OpenFreeMap "Liberty", `https://tiles.openfreemap.org/styles/liberty` |

### Why a release-variant APK and not an `expo-dev-client` development build

A development build in Expo's sense (`expo-dev-client`) does not contain the app's JavaScript. It
loads it from a development server: the Expo guide's next step after installing the build is
"Start the JavaScript bundler" with `npx expo start` ✅
(<https://docs.expo.dev/develop/development-builds/introduction/>). The owner has no machine that
can run that server (the work PC allows no installs; Codespaces is blocked;
`docs/build-prompts.md` section 1). A development build would therefore open on the phone and
show only the launcher.

The spike builds the **release variant** instead: the same native code (MapLibre included), with
the JavaScript bundled into the APK, so it runs on the phone with nothing else. This still proves
what the development build was meant to prove: native modules that Expo Go cannot load work in
our own build. ADR 008 decision 2 ("development builds first") is amended accordingly (see the
addendum in ADR 008). A development build becomes useful only if the owner later has a machine
that can run `npx expo start`.

### Signing

Expo's guide says local `--variant release` builds "are not signed and you cannot submit them to
app stores" ✅ (<https://docs.expo.dev/guides/local-app-development/>). In fact the Android
project that `expo prebuild` generates signs the release variant with the template's
`debug.keystore` (`signingConfig signingConfigs.debug`, comment: "Caution! In production, you
need to generate your own keystore file"). That key is the public React Native debug key
(`CN=Android Debug`, SHA-256 `FA:C6:17:45:DC:09:03:78:6F:B9:ED:E6:2A:96:2B:39:9F:73:48:F0:BB:6F:89:9B:83:32:66:75:91:03:3B:9C`,
read from the generated project on 2026-11-12). Consequences:

- Android accepts the APK for sideloading, and each new spike build installs over the previous
  one because the key is the same.
- The key is public, so anyone could sign an APK that Android would accept as an update. That is
  acceptable for a throwaway spike only. **Phase 1 or Phase 9 must create the project's own
  keystore, keep it as a GitHub Actions secret, and inject it with a config plugin or Gradle
  properties**, never by hand-editing the native project. The first install of a build signed with
  the new key requires uninstalling the spike build.

## 3. Owner's installation steps (Android phone, no computer software needed)

Done once per build. The phone needs internet access for the map.

1. On the work PC, open <https://github.com/sandiaes/Detour/actions> in the browser and sign in.
2. Click the workflow **Spike S1 map APK** on the left, then the most recent run with a green
   tick.
3. Scroll to **Artifacts** at the bottom and click **detour-s1-map-apk**. A zip file downloads.
   (Artifacts expire after 14 days; re-run the workflow to get a new one.)
4. Move the zip to the phone. Two ways, pick one:
   - Open the same GitHub page in the phone's browser (signed in to GitHub) and download the
     artifact directly there; or
   - email the zip to yourself or put it in a cloud drive, and open it on the phone.
5. On the phone, open the zip in the **Files** app and extract it. It contains
   `detour-s1-map.apk` and `build-info.txt`.
6. Tap `detour-s1-map.apk`. Android asks to allow installs from this source (the Files app or the
   browser): tap **Settings**, switch on **Allow from this source**, go back, tap **Install**.
   The exact wording differs between phone makers.
7. If Google Play Protect warns about an unknown app, choose **More details → Install anyway**.
   It warns because the app is not from a store and is signed with a debug key (section 2).
8. Open **Detour S1 map spike**. Expected screen: a street map of Florence; a white box at the top
   saying `Map: loaded`, `Config: bundled stand-in (spike-s1-2026-11-12)` and the style URL; the
   credit line "OpenFreeMap © OpenMapTiles Data from OpenStreetMap" bottom left, which shrinks to
   an "i" button after five seconds or when you move the map.
9. Pinch and pan to check the map redraws. Tap "i" to bring the credits back; tap a credit to open
   its web page.
10. Report back: the phone model and Android version, whether the map appeared, and what the top
    box says. If it says `Map: FAILED to load`, note whether the phone was on the work network
    (which might block `tiles.openfreemap.org`).

To remove it: long-press the app icon → **Uninstall**. The installer permission can be switched
off again in the phone's settings.

## 4. How the style URL reaches the app

The style URL and the attribution lines are **not constants in the app**. They are fields of the
backend's client configuration (`architecture.md` section 4.2, resource "config"). The only
value fixed at build time is the backend's base URL.

```json
GET /v1/config
{
  "config_version": "spike-s1-2026-11-12",
  "map": {
    "style_url": "https://tiles.openfreemap.org/styles/liberty",
    "attribution": [
      { "text": "OpenFreeMap", "url": "https://openfreemap.org" },
      { "text": "© OpenMapTiles", "url": "https://www.openmaptiles.org/" },
      { "text": "Data from OpenStreetMap", "url": "https://www.openstreetmap.org/copyright" }
    ]
  }
}
```

- `spikes/s1-map/src/config.ts` reads `EXPO_PUBLIC_DETOUR_API_URL` (inlined by Expo when the APK
  is built, from the workflow input `api_url`), requests `<api>/v1/config` with a 75-second
  timeout (the Render free tier takes about a minute to wake, ADR 005), validates the shape
  (`style_url` must be HTTPS, attribution must not be empty) and passes `map.style_url` to
  `<Map mapStyle=…>`. On failure it shows the error and a Retry button; it never falls back to a
  built-in URL.
- **Spike-only gap:** there is no backend yet, so an APK built without `api_url` reads the same
  JSON from a bundled file, `spikes/s1-map/spike-config.json`, and the screen says
  `Config: bundled stand-in`. Phase 1 (Prompt 2, item 1) deletes the stand-in and serves this
  object from the FastAPI config endpoint; switching to the PMTiles fallback (D8) is then a
  backend configuration change, not an app release.
- The tile requests themselves go from the phone to `tiles.openfreemap.org`, which the
  architecture allows ("The mobile app calls only the Detour backend and the map tile host").

## 5. Attribution shown

| Where | What | Rule it meets |
|---|---|---|
| Bottom-left of the map, visible at start | "OpenFreeMap", "© OpenMapTiles", "Data from OpenStreetMap", each a link, text from the config | OpenFreeMap requires exactly this credit ✅ (<https://openfreemap.org/quick_start/>); OSMF: attribution "should not require individuals to interact with the map … to see the attribution" and "should typically appear in a corner of the map" ✅ (<https://osmfoundation.org/wiki/Licence/Attribution_Guidelines>) |
| Same place after 5 s or the first pan or zoom | An "i" button that brings the credits back | OSMF allows collapsing "automatically on map interaction" or "automatically after five seconds" if the user can still find it, "for example from an '(i)' button in the corner of the map" ✅ |
| Bottom-right | MapLibre's own attribution button (`attribution` prop), which lists the style's source credits | Kept as a second route; not relied on alone, because it needs a tap |
| — | MapLibre logo | Switched off (`logo={false}`); no licence read requires it |

Not done in the spike, required later: the About screen with the full list including GeoNames
(Phase 5/9).

## 6. If the build cannot run in GitHub Actions: Expo's cloud build

Not needed, since the GitHub Actions build works (section 1). Recorded as the fallback if GitHub
Actions stops being usable (for example, minutes run out in a private repository). Read on 2026-11-12 ✅ (<https://expo.dev/pricing>,
<https://docs.expo.dev/billing/plans/>):

- Free plan: "Up to 15 Android and 15 iOS builds" per month; "Low priority" queue, "At peak times,
  you may experience wait times of 90+ minutes"; "45-minute build timeout"; "These limits reset
  monthly"; "Free plan accounts cannot incur overage charges".
- Whether a payment card is needed for the free plan: not stated on the pages read.
- It needs an Expo account and the `eas` CLI, which can itself run in a GitHub Actions job with an
  Expo access token stored as a secret, so the owner would still need no local software.

## 7. Limits relied on (read 2026-11-12)

| Figure | Source |
|---|---|
| Ubuntu 24.04 runner image includes the Android SDK at `/usr/local/lib/android/sdk` (build-tools 34.0.0 to 37.0.0, platforms android-34 to android-37.x, NDK 27.3 default) and JDK 17 as default | ✅ <https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md> (image 20261101) |
| SDK 58: React Native 0.88, minimum Node 22.13.x, Android 7+, compileSdk 37, targetSdk 36; JDK 17 | ✅ <https://docs.expo.dev/versions/latest/>, <https://docs.expo.dev/get-started/set-up-your-environment/> |
| Linux x64 runner $0.006 per minute, drawn from $12 of included usage on GitHub Free for private repositories | ✅ <https://docs.github.com/en/billing/concepts/product-billing/github-actions> |
| Artifact storage 500 MB on GitHub Free, shared with Packages | ✅ <https://docs.github.com/en/actions/reference/limits> |
| Default artifact retention and maximum artifact size | ✗ not stated on the pages read; the workflow sets 14 days explicitly |
| MapLibre React Native cannot be used in Expo Go; install with the config plugin | ✅ <https://github.com/maplibre/maplibre-react-native/blob/main/docs/content/setup/expo.md> (maplibre.org itself was not reachable) |
| OpenFreeMap needs no key or registration on the pages read; ToS last updated 2026-10-14 | ✅ <https://openfreemap.org/quick_start/>, <https://openfreemap.org/tos/> |

## 8. Open items

- Confirm on the phone that the credit line shows at start, collapses to "i" after five seconds
  or on panning, and comes back when "i" is tapped (section 5). Not yet reported.
- Own signing key before any build that is kept (section 2).
- Only `arm64-v8a` is built, to keep the APK small. Nearly all current phones use it; an older
  32-bit phone would need `armeabi-v7a` added.
- OpenFreeMap asks for a unique User-Agent only for offline downloads; normal map display was not
  given one. MapLibre's `TransformRequestManager.addHeader` can add one in Phase 5 if wanted.
