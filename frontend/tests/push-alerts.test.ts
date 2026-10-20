import { describe, expect, it } from "vitest";
import { keyBytes } from "../src/components/PushAlerts";

describe("push alerts (#266)", () => {
  it("decodes a base64url VAPID key to the 65-byte uncompressed point", () => {
    const key = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM";
    const bytes = keyBytes(key);
    expect(bytes.length).toBe(65);
    expect(bytes[0]).toBe(4);
  });
});
