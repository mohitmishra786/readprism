// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeItem } from "./helpers";

const push = vi.fn();
const api = vi.hoisted(() => ({
  feedback: {
    interaction: vi.fn(() => Promise.resolve({})),
    adjustInterests: vi.fn(() => Promise.resolve({})),
    getInteraction: vi.fn(() => Promise.resolve(null)),
  },
}));
vi.mock("../src/lib/api", () => ({ api }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

import { ContentCard } from "../src/components/digest/ContentCard";

const breakdown = {
  semantic: 0.6,
  source_trust: 0.3,
  novelty: 0.1,
  explanation: "Close to your interest in compilers",
};

describe("ContentCard", () => {
  it("shows the title, AI-labelled summary and a Why button", () => {
    render(<ContentCard content={makeItem()} signalBreakdown={breakdown} />);
    expect(screen.getByRole("link", { name: "How compilers lower loops" })).toBeInTheDocument();
    expect(screen.getByText("AI summary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /why this/i })).toBeInTheDocument();
  });

  it("opens the why panel with the explanation and contribution bars", async () => {
    render(<ContentCard content={makeItem()} signalBreakdown={breakdown} />);
    await userEvent.click(screen.getByRole("button", { name: /why this/i }));
    expect(screen.getByText("Why this is ranked here")).toBeInTheDocument();
    expect(screen.getByText("Close to your interest in compilers")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument(); // semantic share of 0.6/1.0
    expect(screen.getByText("30%")).toBeInTheDocument();
  });

  it("toggles between the brief and detailed summary", async () => {
    render(<ContentCard content={makeItem()} />);
    expect(screen.getByText("A brief summary.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show detailed takeaway" }));
    expect(screen.getByText("A detailed takeaway.")).toBeInTheDocument();
  });

  it("navigates to the reader on title click", async () => {
    render(<ContentCard content={makeItem({ id: "abc" })} />);
    await userEvent.click(screen.getByRole("link", { name: "How compilers lower loops" }));
    expect(push).toHaveBeenCalledWith("/read/abc");
  });

  it("labels discovery items with where they came from", () => {
    render(
      <ContentCard
        content={makeItem()}
        isDiscovery
        signalBreakdown={{ discovered_via: "a link in Simon Willison's blog" }}
      />,
    );
    expect(screen.getByText(/found via a link in Simon Willison's blog/)).toBeInTheDocument();
  });

  it("labels quiet-day catch-up items", () => {
    render(<ContentCard content={makeItem()} signalBreakdown={{ fallback_reason: "quiet" }} />);
    expect(screen.getByText(/Catch-up/)).toBeInTheDocument();
  });

  it("rates and saves through the feedback bar", async () => {
    render(<ContentCard content={makeItem({ id: "x1" })} />);
    await userEvent.click(screen.getByTitle("Helpful"));
    expect(api.feedback.interaction).toHaveBeenCalledWith({ content_item_id: "x1", explicit_rating: 1 });
    await userEvent.click(screen.getByTitle("Save for later"));
    expect(api.feedback.interaction).toHaveBeenCalledWith({ content_item_id: "x1", saved: true });
  });

  it("adjusts the top topic from the card", async () => {
    render(<ContentCard content={makeItem()} />);
    await userEvent.click(screen.getByTitle("More like this (compilers)"));
    expect(api.feedback.adjustInterests).toHaveBeenCalledWith("compilers", "boost");
  });
});
