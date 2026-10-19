import { describe, expect, it } from "vitest";
import { kindOf, summarize } from "../src/components/onboarding/ImportPanel";

describe("onboarding import (#150)", () => {
  it("routes files to the right import", () => {
    expect(kindOf("feedly.opml")).toBe("feeds");
    expect(kindOf("Inoreader-Subscriptions.XML")).toBe("feeds");
    expect(kindOf("ril_export.html")).toBe("saved");
    expect(kindOf("instapaper-export.csv")).toBe("saved");
  });
  it("summarises like '41 feeds, 120 saved articles'", () => {
    expect(summarize(41, 120)).toBe("Imported 41 feeds, 120 saved articles.");
    expect(summarize(1, 0)).toBe("Imported 1 feed.");
    expect(summarize(0, 0)).toBe("Nothing new to import.");
  });
});
