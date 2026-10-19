// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeItem } from "./helpers";

const api = vi.hoisted(() => ({
  feedback: {
    interaction: vi.fn(() => Promise.resolve({})),
    adjustInterests: vi.fn(() => Promise.resolve({})),
    getInteraction: vi.fn(() => Promise.resolve(null)),
  },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { NoTextFallback } from "../src/components/reader/NoTextFallback";

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => vi.useRealTimers());

describe("NoTextFallback (#157)", () => {
  it("shows the summary, rating controls and the original link", () => {
    render(<NoTextFallback item={makeItem()} />);
    expect(screen.getByText("A detailed takeaway.")).toBeInTheDocument();
    expect(screen.getByTitle("Helpful")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open original at example.com/ })).toBeInTheDocument();
  });

  it("labels paywalled items and asks to rate the premise", () => {
    render(<NoTextFallback item={makeItem({ paywalled: true })} />);
    expect(screen.getByText("Paywalled")).toBeInTheDocument();
    expect(screen.getByText("Rate the premise:")).toBeInTheDocument();
    expect(screen.getByText(/behind a paywall on example.com/)).toBeInTheDocument();
  });

  it("explains withheld text on hosted", () => {
    render(<NoTextFallback item={makeItem({ full_text_withheld: true })} />);
    expect(screen.getByText("Read the full article on example.com.")).toBeInTheDocument();
  });

  it("records the outbound click without learning, then asks on return", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<NoTextFallback item={makeItem({ id: "p1" })} />);
    await user.click(screen.getByRole("link", { name: /Open original/ }));
    expect(api.feedback.interaction).toHaveBeenCalledWith({ content_item_id: "p1", opened_externally: true });

    act(() => setVisibility("hidden"));
    vi.advanceTimersByTime(20_000);
    act(() => setVisibility("visible"));
    expect(await screen.findByRole("dialog", { name: "Did you finish it?" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Yes, all of it" }));
    expect(api.feedback.interaction).toHaveBeenLastCalledWith({
      content_item_id: "p1",
      read_completion_pct: 1,
      reached_end: true,
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not ask after a quick glance away", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<NoTextFallback item={makeItem()} />);
    await user.click(screen.getByRole("link", { name: /Open original/ }));
    act(() => setVisibility("hidden"));
    vi.advanceTimersByTime(3_000);
    act(() => setVisibility("visible"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
