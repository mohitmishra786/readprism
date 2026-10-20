// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Source } from "../src/lib/types";
import { NewsletterSenderHelp } from "../src/components/sources/NewsletterSenderHelp";

const sender = (over: Partial<Source>): Source =>
  ({ id: "n1", url: "newsletter://u/x", name: "Weekly Rust", source_type: "newsletter", is_active: true,
     trust_weight: 0.5, health: "healthy", ...over }) as Source;

describe("newsletter inbox relief (#249)", () => {
  it("offers the sender's unsubscribe link for a forwarded copy, opened safely", () => {
    render(<NewsletterSenderHelp source={sender({ newsletter_delivery: "forwarded",
      unsubscribe_options: { url: "https://rust.example/unsub", mailto: "mailto:stop@rust.example" } })} />);
    const link = screen.getByRole("link", { name: "unsubscribe page" });
    expect(link).toHaveAttribute("href", "https://rust.example/unsub");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByRole("link", { name: "email the sender" })).toHaveAttribute("href", "mailto:stop@rust.example");
    expect(screen.getByText(/Do step 1 first/)).toBeInTheDocument();
  });
  it("falls back to instructions when the sender gave no link", () => {
    render(<NewsletterSenderHelp source={sender({ newsletter_delivery: "forwarded", unsubscribe_options: null })} />);
    expect(screen.getByText(/link at the bottom of any issue/)).toBeInTheDocument();
  });
  it("says there's nothing to do for a direct subscription", () => {
    render(<NewsletterSenderHelp source={sender({ newsletter_delivery: "direct" })} />);
    expect(screen.getByText(/nothing in your inbox to clean up/)).toBeInTheDocument();
  });
  it("shows nothing for feeds or unknown delivery", () => {
    const { container } = render(<NewsletterSenderHelp source={sender({ source_type: "rss", newsletter_delivery: "forwarded" })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
