// Base64 without relying on the platform (Hermes, Node and browsers differ): the cover picture
// travels to and from the backend as base64 in JSON (ADR 034, step 5).

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const LOOKUP = new Map([...ALPHABET].map((c, i) => [c, i]));

export function encodeBase64(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i] ?? 0;
    const b = bytes[i + 1];
    const c = bytes[i + 2];
    const n = (a << 16) | ((b ?? 0) << 8) | (c ?? 0);
    out += ALPHABET[(n >> 18) & 63];
    out += ALPHABET[(n >> 12) & 63];
    out += b === undefined ? "=" : ALPHABET[(n >> 6) & 63];
    out += c === undefined ? "=" : ALPHABET[n & 63];
  }
  return out;
}

export function decodeBase64(text: string): Uint8Array {
  const clean = text.replace(/[^A-Za-z0-9+/]/g, "");
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const v = [0, 1, 2, 3].map((k) => LOOKUP.get(clean[i + k] ?? "") ?? -1);
    const n =
      ((v[0] ?? 0) << 18) |
      ((v[1] ?? 0) << 12) |
      (Math.max(v[2] ?? 0, 0) << 6) |
      Math.max(v[3] ?? 0, 0);
    if (o < out.length) out[o++] = (n >> 16) & 255;
    if ((v[2] ?? -1) >= 0 && o < out.length) out[o++] = (n >> 8) & 255;
    if ((v[3] ?? -1) >= 0 && o < out.length) out[o++] = n & 255;
  }
  return out.subarray(0, o);
}
