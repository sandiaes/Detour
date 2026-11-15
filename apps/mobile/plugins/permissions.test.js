// The app never asks for the phone's location or to draw over other apps (docs/privacy.md). MapLibre
// and Expo declare those permissions in their own manifests; app.json removes them from the APK
// with Expo's blockedPermissions (no native project is edited).
const app = require("../app.json");

test("location and drawing over other apps are removed from the APK", () => {
  expect(app.expo.android.blockedPermissions).toEqual(
    expect.arrayContaining([
      "android.permission.ACCESS_COARSE_LOCATION",
      "android.permission.ACCESS_FINE_LOCATION",
      "android.permission.SYSTEM_ALERT_WINDOW",
    ]),
  );
});

test("Android's automatic cloud backup is off: documents stay on the phone (ADR 023)", () => {
  expect(app.expo.android.allowBackup).toBe(false);
});
