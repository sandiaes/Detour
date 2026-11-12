# ADR 008 — No app stores: Android by APK, iPhone built on the owner's Mac

- **Status:** Accepted on 2026-11-12 (owner decision).
- **Date:** 2026-11-12
- **Related:** [`001-technology-stack.md`](001-technology-stack.md), [`../app-plan.md`](../app-plan.md) (S1, Phase 11)

## Context

The owner does not want the app in any app store and, on past projects, ran apps on a phone
through Expo Go. Detour cannot use Expo Go: MapLibre React Native is a native library outside
Expo Go (ADR 001, `api-evaluation.md`), so a **development build** is required.

## What the official sources say (read 2026-11-12)

- ✅ A development build is "essentially your own version of Expo Go where you are free to use
  any native libraries". <https://docs.expo.dev/develop/development-builds/introduction/>
- ✅ Builds can be compiled locally with the native toolchain, or in Expo's cloud service.
  Compiling locally with Expo CLI needs no Expo account and "is the only way to install a
  development build on an iPhone without a paid Apple Developer account".
  <https://docs.expo.dev/develop/development-builds/create-a-build/>
- ✅ iOS ad hoc distribution "requires a paid Apple Developer account" and is limited to at most
  100 iPhones per year, each registered by UDID.
  <https://docs.expo.dev/build/internal-distribution/>
- ✗ Not verified: that Xcode is needed for the local iPhone build (taken from the page's
  prerequisite line and general knowledge; the host-support table was not readable as text);
  how long an app signed with a free Apple ID stays valid; the free-plan limits of Expo's cloud
  build service; whether GitHub Actions can build the Android APK for this project.

## Decision

1. The app is **not distributed through any app store** (neither Google Play nor the App Store).
2. **Android:** the app is installed as an APK on the owner's phone (sideloading). Development
   builds first; a release-mode APK later. Builds run in GitHub Actions if that works (to be
   proved in spike S1), otherwise locally or in Expo's cloud service.
3. **iPhone (Phase 11):** the app is compiled on the owner's Mac with Xcode and installed on the
   owner's iPhone over a cable. Whether a free Apple ID is enough in practice, or the paid Apple
   Developer Program ($99 per year) is worth paying, is decided in Phase 11 after the current
   Apple limits are verified.
4. Updates are installed by hand (a new APK, a new build); there are no store updates.

## Alternatives

| Alternative | Why not |
|---|---|
| Google Play and App Store | Rejected by the owner; Google Play needs a $25 fee and a closed test with 12 testers for 14 days for new personal accounts (`architecture.md`), the App Store needs $99 per year. |
| Expo Go | Cannot load native libraries such as MapLibre. |

## Consequences

- Platform costs are zero for Android. iOS costs nothing if the free route works; otherwise $99
  per year, optional.
- The owner needs a Mac for iPhone builds (owner confirmed access).
- No store review, but also no automatic updates and no distribution to other people without the
  same manual steps (an Android APK can be shared; an iPhone build cannot, short of the paid
  ad hoc route).
