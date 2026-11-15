const { addReleaseSigning } = require("./withReleaseSigning");

// The signing part of the build.gradle that `expo prebuild` writes for SDK 58
// (expo-template-bare-minimum 58.0.34), trimmed.
const TEMPLATE = `android {
    signingConfigs {
        debug {
            storeFile file('debug.keystore')
            storePassword 'android'
            keyAlias 'androiddebugkey'
            keyPassword 'android'
        }
    }
    buildTypes {
        debug {
            signingConfig signingConfigs.debug
        }
        release {
            // Caution! In production, you need to generate your own keystore file.
            signingConfig signingConfigs.debug
            minifyEnabled enableMinifyInReleaseBuilds
        }
    }
}
`;

test("the release build uses the project's key when the build provides one", () => {
  const out = addReleaseSigning(TEMPLATE);
  expect(out).toContain('storeFile file(System.getenv("DETOUR_KEYSTORE_FILE"))');
  expect(out).toContain(
    'signingConfig(System.getenv("DETOUR_KEYSTORE_FILE") ? signingConfigs.release : signingConfigs.debug)',
  );
  // The debug build type keeps the debug key.
  expect(out).toMatch(/debug \{\n\s+signingConfig signingConfigs\.debug\n/);
  // No secret is written into the file: only environment variable names.
  expect(out).not.toMatch(/storePassword '(?!android')/);
});

test("running twice changes nothing more", () => {
  const once = addReleaseSigning(TEMPLATE);
  expect(addReleaseSigning(once)).toBe(once);
});

test("fails loudly when the template changes shape", () => {
  expect(() => addReleaseSigning("android {}")).toThrow(/signingConfigs/);
});

test("app.config.js always applies it", () => {
  const appConfig = require("../app.config.js");
  const out = appConfig({ config: { plugins: ["@maplibre/maplibre-react-native"] } });
  expect(out.plugins).toContain("./plugins/withReleaseSigning");
});
