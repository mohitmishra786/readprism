import { describe, expect, it } from "vitest";
import { elapsedSeconds } from "../src/components/NewsletterAddressCard";

describe("newsletter address test (#151)", () => {
  it("reports how long the test took to arrive", () => {
    expect(elapsedSeconds("2026-10-20T10:00:00Z", "2026-10-20T10:00:12Z")).toBe(12);
  });
});
