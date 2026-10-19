import { describe, expect, it } from "vitest";
import { finishedPhrase } from "../src/components/reader/GotItToast";

describe("post-read toast (#228)", () => {
  it("rounds active time to whole minutes, at least one", () => {
    expect(finishedPhrase(4.4 * 60_000)).toBe("You finished this in 4 min");
    expect(finishedPhrase(20_000)).toBe("You finished this in 1 min");
  });
});
