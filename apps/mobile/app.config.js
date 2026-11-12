// Extends app.json. Only the end-to-end build (DETOUR_E2E=1, .github/workflows/e2e-android.yml)
// differs: it allows plain HTTP to the backend on the CI runner. Every other build is unchanged.
module.exports = ({ config }) => ({
  ...config,
  plugins: [
    ...(config.plugins ?? []),
    ...(process.env.DETOUR_E2E === "1" ? ["./plugins/withCleartextTraffic"] : []),
  ],
});
