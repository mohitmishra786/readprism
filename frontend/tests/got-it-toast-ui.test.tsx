// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ feedback: { adjustInterests: vi.fn(() => Promise.resolve({})) } }));
vi.mock("../src/lib/api", () => ({ api }));

import { GotItToast } from "../src/components/reader/GotItToast";

describe("GotItToast", () => {
  it("offers more of the topic after a full read", async () => {
    render(<GotItToast topic="compilers" activeTimeMs={240_000} onClose={() => {}} />);
    expect(screen.getByText(/You finished this in 4 min/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    expect(api.feedback.adjustInterests).toHaveBeenCalledWith("compilers", "boost");
    expect(screen.getByText("Got it: more compilers.")).toBeInTheDocument();
  });

  it("Less suppresses the topic", async () => {
    render(<GotItToast topic="crypto" activeTimeMs={60_000} onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Less" }));
    expect(api.feedback.adjustInterests).toHaveBeenCalledWith("crypto", "suppress");
  });

  it("can be dismissed without adjusting anything", async () => {
    const onClose = vi.fn();
    render(<GotItToast topic="x" activeTimeMs={1000} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onClose).toHaveBeenCalled();
    expect(api.feedback.adjustInterests).not.toHaveBeenCalled();
  });
});
