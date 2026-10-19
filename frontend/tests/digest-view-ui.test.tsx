// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Digest } from "../src/lib/types";
import { makeItem } from "./helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
const ok = vi.hoisted(() => () => Promise.resolve(null));
vi.mock("../src/lib/api", () => ({
  api: {
    feedback: { getInteraction: ok, interaction: ok, adjustInterests: ok },
    digest: { prompts: () => Promise.resolve([]), answerPrompt: ok, dismissPrompt: ok, markOpened: ok, emerging: () => Promise.resolve([]) },
  },
}));

import { DigestView } from "../src/components/digest/DigestView";

function digest(breakdown: Record<string, string | number>): Digest {
  return {
    id: "d1",
    user_id: "u1",
    generated_at: "2026-10-20T07:00:00Z",
    delivered_at: null,
    delivery_method: "in_app",
    section_counts: { lead: 1 },
    opened: false,
    total_items: 1,
    created_at: "2026-10-20T07:00:00Z",
    items: [
      {
        id: "di1",
        digest_id: "d1",
        content_item_id: "item-1",
        position: 0,
        section: "lead",
        prs_score: 0.7,
        signal_breakdown: breakdown,
        content: makeItem(),
      },
    ],
  };
}

describe("DigestView", () => {
  it("explains a quiet-day catch-up edition (#142)", () => {
    render(<DigestView digest={digest({ fallback_reason: "quiet" })} />);
    expect(screen.getByText(/Your sources were quiet today/)).toBeInTheDocument();
  });

  it("shows the item count and no banner on a normal day", () => {
    render(<DigestView digest={digest({ semantic: 0.5 })} />);
    expect(screen.getByText(/1 items/)).toBeInTheDocument();
    expect(screen.queryByText(/Your sources were quiet today/)).not.toBeInTheDocument();
  });
});
