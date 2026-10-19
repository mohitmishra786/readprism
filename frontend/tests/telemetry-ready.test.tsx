// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../src/lib/api", () => ({
  api: { feedback: { interaction: vi.fn(() => Promise.resolve({})) } },
  keepalivePost: vi.fn(),
}));

import { useReadingTelemetry } from "../src/lib/useReadingTelemetry";

const nextFrame = () => new Promise((r) => requestAnimationFrame(() => r(null)));

describe("reading telemetry before the article loads (#193)", () => {
  it("does not count the loading shell as fully scrolled", async () => {
    // jsdom pages "fit in the viewport", which is what the loading shell
    // looked like: the hook used to record 100% scroll depth on every open.
    const { result } = renderHook(() =>
      useReadingTelemetry({ contentItemId: "a", readingTimeMinutes: 10, ready: false }),
    );
    await act(async () => {
      window.dispatchEvent(new Event("scroll"));
      await nextFrame();
    });
    expect(result.current.snapshot.scrollDepthPct).toBe(0);
    expect(result.current.snapshot.readingProgressPct).toBe(0);
  });

  it("measures once the article is on screen", async () => {
    const { result, rerender } = renderHook(
      ({ ready }) => useReadingTelemetry({ contentItemId: "a", readingTimeMinutes: 10, ready }),
      { initialProps: { ready: false } },
    );
    rerender({ ready: true });
    await act(nextFrame);
    expect(result.current.snapshot.scrollDepthPct).toBe(1); // a genuinely short article
  });
});
