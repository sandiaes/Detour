// Extends app.json. Every build gets the release-signing plugin, which signs with the project's
// own key only when the build provides one (docs/android-release.md). Only the end-to-end build
// (DETOUR_E2E=1, .github/workflows/e2e-android.yml) also allows plain HTTP to the backend on the
// CI runner.
module.exports = ({ config }) => ({
  ...config,
  plugins: [
    ...(config.plugins ?? []),
    "./plugins/withReleaseSigning",
    ...(process.env.DETOUR_E2E === "1" ? ["./plugins/withCleartextTraffic"] : []),
  ],
});
