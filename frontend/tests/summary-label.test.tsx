// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SummaryLabel } from "../src/components/SummaryLabel";

describe("SummaryLabel", () => {
  it("labels LLM summaries", () => {
    render(<SummaryLabel source="llm" />);
    expect(screen.getByText("AI summary")).toBeInTheDocument();
  });
  it("shows nothing for extractive or unknown summaries", () => {
    const { container } = render(<SummaryLabel source="extractive" />);
    expect(container).toBeEmptyDOMElement();
    const none = render(<SummaryLabel source={null} />);
    expect(none.container).toBeEmptyDOMElement();
  });
});
