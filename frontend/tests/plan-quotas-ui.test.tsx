// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => vi.fn());
vi.mock("../src/lib/api", () => ({ api: { billing: { state } } }));

import { PlanSection } from "../src/components/PlanSection";

const base = {
  billing_enabled: false,
  status: "active",
  trial_ends_at: null,
  trial_days_left: null,
  plan_expires_at: null,
  can_manage: false,
};

describe("plan quotas (#172)", () => {
  it("lists limits and use, flagging a used-up allowance", async () => {
    state.mockResolvedValueOnce({
      ...base,
      plan: "pro",
      quotas: [
        { quota: "sources", limit: 500, used: 42, daily: false },
        { quota: "llm_summaries_per_day", limit: 200, used: 200, daily: true },
        { quota: "creators", limit: 0, used: 3, daily: false },
      ],
    });
    render(<PlanSection />);
    expect(await screen.findByText("42 of 500")).toBeInTheDocument();
    expect(screen.getByText("200 of 200")).toHaveStyle({ color: "#dc2626" });
    expect(screen.getByText("3 (no limit)")).toBeInTheDocument();
    expect(screen.getByText(/reset at midnight UTC/)).toBeInTheDocument();
  });

  it("renders nothing on self-host", async () => {
    state.mockResolvedValueOnce({ ...base, plan: "selfhost", quotas: [] });
    const { container } = render(<PlanSection />);
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
