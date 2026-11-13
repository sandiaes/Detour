#!/usr/bin/env bash
# Runs inside the emulator step of .github/workflows/e2e-android.yml (the emulator action runs one
# shell line at a time, so the logic lives in a script). On failure it prints what was on screen,
# the app's log lines and the API's log into the job log, so a failure can be read without
# downloading anything.
set -u
TMP="${RUNNER_TEMP:-/tmp}"

adb install "$TMP/app-release.apk" || exit 1
# Do not show "isn't responding" dialogs (System UI, the launcher) on this slow emulator.
adb shell settings put global hide_error_dialogs 1
adb shell settings put secure anr_show_background 0
# Let the freshly booted system settle before the first screen is driven.
sleep 30
maestro test --format junit --output "$TMP/maestro-report.xml" \
  --debug-output "$TMP/maestro-debug" apps/mobile/e2e/trip-flow.yaml
status=$?

if [ "$status" -ne 0 ]; then
  echo "::group::Texts on the screen at the failure"
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  adb shell cat /sdcard/ui.xml 2>/dev/null | grep -oE '(text|content-desc|resource-id)="[^"]+"' | head -80
  echo "::endgroup::"
  adb exec-out screencap -p > "$TMP/screen.png" 2>/dev/null
  adb logcat -d > "$TMP/logcat.txt" 2>/dev/null
  echo "::group::App log lines (errors, React Native, network)"
  grep -E "AndroidRuntime|FATAL|ReactNative|ReactNativeJS|io\.github\.sandiaes|CLEARTEXT|UnknownHost|Network request failed" "$TMP/logcat.txt" | tail -120
  echo "::endgroup::"
  echo "::group::API log (tail)"
  tail -40 "$TMP/api.log" 2>/dev/null
  echo "::endgroup::"
fi
exit "$status"
