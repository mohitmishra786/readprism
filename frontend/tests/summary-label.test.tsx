// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SummaryLabel } from "../src/components/SummaryLabel";

describe("SummaryLabel", () => {
  it("labels LLM summaries", () => {
    render(<SummaryLabel source="llm" />);
    expect(screen.getByText("AI summary")).toBeInTheDocument();
  });
  it("labels extractive summaries as a quick summary (#261)", () => {
    render(<SummaryLabel source="extractive" />);
    expect(screen.getByText("Quick summary")).toBeInTheDocument();
    expect(screen.queryByText("AI summary")).not.toBeInTheDocument();
  });
  it("shows nothing when the source is unknown", () => {
    for (const source of [null, undefined, "feed"]) {
      const { container, unmount } = render(<SummaryLabel source={source} />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });

  it("marks summaries of an episode's transcript (#252)", () => {
    render(<SummaryLabel source="extractive" fromTranscript />);
    expect(screen.getByText("Quick summary · transcript")).toBeInTheDocument();
  });
});
