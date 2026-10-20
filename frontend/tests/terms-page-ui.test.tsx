// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TermsPage from "../src/app/terms/page";
import sitemap from "../src/app/sitemap";
import { PlanSection } from "../src/components/PlanSection";

const state = vi.hoisted(() => vi.fn());
const checkout = vi.hoisted(() => vi.fn(() => Promise.reject(new Error("no"))));
vi.mock("../src/lib/api", () => ({ api: { billing: { state, checkout, portal: vi.fn() } } }));

describe("Terms page and links (#178)", () => {
  it("renders Terms of Service with notice and all standard sections", () => {
    render(<TermsPage />);
    expect(screen.getByRole("heading", { name: "ReadPrism Terms of Service", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/Template: not legal advice/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "The Service", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Accounts", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Acceptable use", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Forwarded content/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Third-party content", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Scraping and automated access/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Paid tiers", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Disclaimers and liability/i, level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Termination", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Changes", level: 2 })).toBeInTheDocument();
  });

  it("includes /terms in the sitemap", () => {
    const map = sitemap();
    const urls = map.map((entry) => entry.url);
    expect(urls.some((u) => u.endsWith("/terms"))).toBe(true);
  });

  it("links terms next to checkout buttons in PlanSection", async () => {
    const q = {
      sources: 500,
      creators: 50,
      newsletters_per_day: 100,
      newsletter_mb_per_day: 50,
      llm_summaries_per_day: 200,
      digest_builds_per_day: 6,
    };
    state.mockResolvedValueOnce({
      billing_enabled: true,
      plan: "trial",
      status: null,
      quotas: [],
      plans: [
        { plan: "reader", name: "Reader", intervals: ["month"], quotas: q },
      ],
    });
    render(<PlanSection />);
    const termsLink = await screen.findByRole("link", { name: "Terms of Service" });
    expect(termsLink).toBeInTheDocument();
    expect(termsLink).toHaveAttribute("href", "/terms");
  });
});
