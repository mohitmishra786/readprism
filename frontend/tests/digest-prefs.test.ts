import { describe, expect, it } from "vitest";
import { digestPreferencesPayload } from "../src/components/onboarding/digestPrefs";

describe("final onboarding step (#201)", () => {
  it("saves an explicit time with the detected timezone", () => {
    expect(
      digestPreferencesPayload({ frequency: "daily", emailOn: true, time: "06:30", timezone: "Asia/Kolkata" }),
    ).toEqual({ digest_frequency: "daily", digest_time_morning: "06:30:00", timezone: "Asia/Kolkata" });
  });
  it("turns email off with the in-app-only frequency", () => {
    expect(
      digestPreferencesPayload({ frequency: "weekly", emailOn: false, time: "7:5", timezone: "UTC" }),
    ).toEqual({ digest_frequency: "in_app_only", digest_time_morning: "07:05:00", timezone: "UTC" });
  });
});
