import { decodeBase64, encodeBase64 } from "./base64";

test("round trips every length and matches the standard encoding", () => {
  for (let n = 0; n < 40; n += 1) {
    const bytes = Uint8Array.from({ length: n }, (_, i) => (i * 37 + n) % 256);
    const text = encodeBase64(bytes);
    expect(text).toBe(Buffer.from(bytes).toString("base64"));
    expect(Array.from(decodeBase64(text))).toEqual(Array.from(bytes));
  }
});
