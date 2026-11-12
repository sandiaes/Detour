const { defineConfig, globalIgnores } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    // Jest's globals, for the setup file and the test doubles (the *.test.* files are already known).
    files: ["jest.setup.js", "src/testing/**", "plugins/**"],
    languageOptions: { globals: { jest: "readonly", test: "readonly", expect: "readonly" } },
  },
  globalIgnores(["android/", "ios/", ".expo/", "coverage/"]),
]);
