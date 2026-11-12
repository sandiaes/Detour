// Config plugin for the end-to-end build only (app.config.js enables it when DETOUR_E2E=1).
// The CI emulator talks to a backend on the runner over plain HTTP (http://10.0.2.2:8000), which
// Android blocks by default in release builds. A normal build never gets this plugin, so the
// app stays HTTPS-only. Native projects are generated, never hand-edited (CLAUDE.md).
const { withAndroidManifest } = require("expo/config-plugins");

function allowCleartext(manifest) {
  const application = manifest.manifest.application?.[0];
  if (!application) throw new Error("AndroidManifest has no <application>");
  application.$["android:usesCleartextTraffic"] = "true";
  return manifest;
}

module.exports = function withCleartextTraffic(config) {
  return withAndroidManifest(config, (c) => {
    c.modResults = allowCleartext(c.modResults);
    return c;
  });
};
module.exports.allowCleartext = allowCleartext;
