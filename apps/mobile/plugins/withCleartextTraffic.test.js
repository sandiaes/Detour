const { allowCleartext } = require("./withCleartextTraffic");

test("marks the application as allowing cleartext traffic", () => {
  const manifest = { manifest: { application: [{ $: { "android:name": ".MainApplication" } }] } };
  const out = allowCleartext(manifest);
  expect(out.manifest.application[0].$["android:usesCleartextTraffic"]).toBe("true");
  expect(out.manifest.application[0].$["android:name"]).toBe(".MainApplication");
});

test("fails loudly without an application element", () => {
  expect(() => allowCleartext({ manifest: {} })).toThrow(/no <application>/);
});
