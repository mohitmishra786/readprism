// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Source } from "../src/lib/types";

vi.mock("../src/lib/api", () => ({ api: { sources: {} } }));
import { SourceList } from "../src/components/sources/SourceList";

const source = (over: Partial<Source>): Source =>
  ({ id: "s1", url: "https://www.youtube.com/feeds/videos.xml?channel_id=UC1", feed_url: null, name: "A channel",
     source_type: "rss", is_active: true, trust_weight: 0.5, health: "healthy", last_error: null, ...over }) as Source;

describe("source health (#240)", () => {
  it("labels a YouTube outage without offering a fix", () => {
    render(<SourceList sources={[source({ health: "platform_outage", last_error: "HTTP 500" })]} onUpdated={() => {}} onDeleted={() => {}} />);
    expect(screen.getByText("Platform outage")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fix this feed" })).not.toBeInTheDocument();
  });
  it("still offers a fix for a failing feed", () => {
    render(<SourceList sources={[source({ health: "failing" })]} onUpdated={() => {}} onDeleted={() => {}} />);
    expect(screen.getByRole("button", { name: "Fix this feed" })).toBeInTheDocument();
  });
});
