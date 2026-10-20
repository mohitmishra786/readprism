// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const account = vi.hoisted(() => ({
  llmKey: vi.fn(),
  saveLlmKey: vi.fn(),
  removeLlmKey: vi.fn(() => Promise.resolve()),
}));
vi.mock("../src/lib/api", () => ({ api: { account } }));

import { LlmKeySection } from "../src/components/LlmKeySection";

const GROQ = "https://api.groq.com/openai/v1";

describe("own LLM key (#255)", () => {
  it("saves a key and then shows only its last 4 characters", async () => {
    account.llmKey.mockResolvedValueOnce({ configured: false, base_url: null, model: null, last4: null, allowed_base_urls: [GROQ] });
    account.saveLlmKey.mockResolvedValueOnce({ configured: true, base_url: GROQ, model: null, last4: "WXYZ" });
    render(<LlmKeySection />);
    await userEvent.type(await screen.findByLabelText("API key"), "sk-secret-123WXYZ");
    await userEvent.click(screen.getByRole("button", { name: "Check and save" }));
    expect(account.saveLlmKey).toHaveBeenCalledWith({ api_key: "sk-secret-123WXYZ", base_url: GROQ, model: undefined });
    expect(await screen.findByText("WXYZ")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-secret-123WXYZ")).toBeNull();
  });

  it("shows the provider's refusal", async () => {
    account.llmKey.mockResolvedValueOnce({ configured: false, base_url: null, model: null, last4: null, allowed_base_urls: [GROQ] });
    account.saveLlmKey.mockRejectedValueOnce(new Error("The provider didn't accept this key and model."));
    render(<LlmKeySection />);
    await userEvent.type(await screen.findByLabelText("API key"), "sk-wrong-key");
    await userEvent.click(screen.getByRole("button", { name: "Check and save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("didn't accept");
  });

  it("renders nothing where the feature is off (self-host)", async () => {
    account.llmKey.mockRejectedValueOnce(new Error("Not available"));
    const { container } = render(<LlmKeySection />);
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
