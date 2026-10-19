// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ digest: { emerging: vi.fn() } }));
vi.mock("../src/lib/api", () => ({ api }));

import { EmergingTopics, emergingLine } from "../src/components/digest/EmergingTopics";

describe("Emerging topics card (#218)", () => {
  it("shows emerging topics linking to a search", async () => {
    api.digest.emerging.mockResolvedValue([
      { topic: "webassembly", recent_sources: 9, baseline_mean: 1.5, z: 4.2 },
      { topic: "raft", recent_sources: 4, baseline_mean: 0, z: 3 },
    ]);
    render(<EmergingTopics />);
    const link = await screen.findByRole("link", { name: "webassembly" });
    expect(link).toHaveAttribute("href", "/search?q=webassembly");
    expect(screen.getByRole("region", { name: "Emerging this week" })).toBeInTheDocument();
    expect(screen.getByText(/9 sources in the last 3 days \(usually about 2 a week\)/)).toBeInTheDocument();
    expect(screen.getByText(/new this month/)).toBeInTheDocument();
  });

  it("is hidden when nothing is emerging, or on error", async () => {
    api.digest.emerging.mockResolvedValue([]);
    const { container } = render(<EmergingTopics />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
    api.digest.emerging.mockRejectedValue(new Error("x"));
    const again = render(<EmergingTopics />);
    await new Promise((r) => setTimeout(r, 0));
    expect(again.container).toBeEmptyDOMElement();
  });

  it("phrases the baseline", () => {
    expect(emergingLine({ topic: "t", recent_sources: 3, baseline_mean: 0.4 })).toContain("new this month");
  });
});
