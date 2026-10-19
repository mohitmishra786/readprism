// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ search: { why: vi.fn() } }));
vi.mock("../src/lib/api", () => ({ api }));

import { WhyNotSeen, sharePercent } from "../src/components/WhyNotSeen";

describe("Why didn't I see this? (#267)", () => {
  it("explains the verdict, the contributions and what would raise it", async () => {
    api.search.why.mockResolvedValue({
      content_id: "c1",
      title: "T",
      score: 0.4,
      explanation: "Close to your interest in compilers",
      why_topics: null,
      verdict: "ranked_below_cutoff",
      message: "It scored 0.40; the lowest item in your latest digest scored 0.55, so it didn't make the cut.",
      latest_digest_cutoff: 0.55,
      contributions: [
        { signal: "semantic", feature: 0.8, weight: 0.3, contribution: 0.24, has_data: true },
        { signal: "source_trust", feature: 0.4, weight: 0.4, contribution: 0.16, has_data: true },
        { signal: "novelty", feature: 0, weight: 0.1, contribution: 0, has_data: false },
      ],
      raise_it: [{ signal: "source_trust", how: "Read and rate articles from this source" }],
    });
    render(<WhyNotSeen contentId="c1" />);
    await userEvent.click(screen.getByRole("button", { name: "Why didn't I see this?" }));
    expect(await screen.findByText(/didn't make the cut/)).toBeInTheDocument();
    expect(screen.getByText(/Score 0.40 · Close to your interest in compilers/)).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.queryByText("expands your reading")).not.toBeInTheDocument(); // zero contribution hidden
    expect(screen.getByText("Read and rate articles from this source")).toBeInTheDocument();
    expect(api.search.why).toHaveBeenCalledWith("c1");
  });

  it("computes each signal's share of the score", () => {
    expect(sharePercent(0.1, 0.4)).toBe(25);
    expect(sharePercent(0.1, 0)).toBe(0);
  });
});
