// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ digest: { vsNewest: vi.fn() } }));
vi.mock("../src/lib/api", () => ({ api }));

import { VsNewestCard, winLine } from "../src/components/digest/VsNewestCard";

describe("Your digest vs newest-first (#237)", () => {
  it("shows the reader's own buried-but-finished articles", async () => {
    api.digest.vsNewest.mockResolvedValue({
      available: true,
      examples: [{ content_id: "c1", title: "How compilers lower loops", digest_date: "2026-10-18", your_position: 1, newest_first_position: 12 }],
      interleaving: { digests: 5, prs_wins: 3, newest_wins: 1, ties: 1 },
    });
    render(<VsNewestCard />);
    expect(await screen.findByRole("link", { name: "How compilers lower loops" })).toHaveAttribute("href", "/read/c1");
    expect(screen.getByText(/#1 in your digest, #12 by date/)).toBeInTheDocument();
    expect(screen.getByText(/your ranking won 3 and newest-first won 1/)).toBeInTheDocument();
  });

  it("is hidden without enough data", async () => {
    api.digest.vsNewest.mockResolvedValue({ available: false, examples: [], interleaving: null });
    const { container } = render(<VsNewestCard />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });

  it("only states a head-to-head result when there is one", () => {
    expect(winLine({ digests: 2, prs_wins: 0, newest_wins: 0, ties: 2 })).toBeNull();
  });
});
