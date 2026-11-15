// Config plugin: sign the release APK with the project's own key when the build provides one
// (ADR 008, "Signing"; docs/android-release.md, "Your own signing key"). Native projects are
// generated, never hand-edited (CLAUDE.md), so the change is made to the generated build.gradle.
//
// The key never enters the repository: the "Android APK" workflow writes the keystore from a
// GitHub secret to a temporary file and passes its path and passwords as environment variables.
// When DETOUR_KEYSTORE_FILE is not set the build is signed with the public debug key, exactly as
// before, so nothing changes until the owner adds the secrets.
const { withAppBuildGradle } = require("expo/config-plugins");

const MARK = "// detour: release signing";

const RELEASE_CONFIG = `        release {
            ${MARK}
            if (System.getenv("DETOUR_KEYSTORE_FILE")) {
                storeFile file(System.getenv("DETOUR_KEYSTORE_FILE"))
                storePassword System.getenv("DETOUR_KEYSTORE_PASSWORD")
                keyAlias System.getenv("DETOUR_KEY_ALIAS")
                keyPassword System.getenv("DETOUR_KEY_PASSWORD")
            }
        }
`;

function addReleaseSigning(gradle) {
  if (gradle.includes(MARK)) return gradle;
  const configs = "    signingConfigs {\n";
  if (!gradle.includes(configs)) throw new Error("build.gradle has no signingConfigs block");
  let out = gradle.replace(configs, configs + RELEASE_CONFIG);
  // The release build type's signing line is the second "signingConfig signingConfigs.debug".
  const releaseType =
    /(buildTypes\s*\{[\s\S]*?release\s*\{[\s\S]*?)signingConfig signingConfigs\.debug/;
  if (!releaseType.test(out)) throw new Error("build.gradle has no release signing line");
  out = out.replace(
    releaseType,
    '$1signingConfig(System.getenv("DETOUR_KEYSTORE_FILE") ? signingConfigs.release : signingConfigs.debug)',
  );
  return out;
}

module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (c) => {
    c.modResults.contents = addReleaseSigning(c.modResults.contents);
    return c;
  });
};
module.exports.addReleaseSigning = addReleaseSigning;
