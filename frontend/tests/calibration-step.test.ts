import { describe, expect, it } from "vitest";
import { hostOf } from "../src/components/onboarding/CalibrationStep";

describe("calibration step (#149)", () => {
  it("shows the source host next to each headline", () => {
    expect(hostOf("https://www.example.com/post/1")).toBe("example.com");
    expect(hostOf("not a url")).toBe("");
  });
});
