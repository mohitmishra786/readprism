// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  setup: { config: vi.fn(), save: vi.fn(), testLlm: vi.fn(), testSmtp: vi.fn() },
}));
vi.mock("../src/lib/api", () => ({ api }));

import SetupPage from "../src/app/(app)/admin/setup/page";

const CONFIG = {
  can_store_secrets: true,
  effective_registration_mode: "closed",
  llm_configured: true,
  email_configured: false,
  fields: [
    { key: "llm_api_key", group: "llm", label: "API key", secret: true, source: "saved", is_set: true },
    { key: "llm_base_url", group: "llm", label: "Base URL", secret: false, source: "env", is_set: true, value: "https://api.groq.com/openai/v1" },
    { key: "llm_model_fast", group: "llm", label: "Fast model", secret: false, source: "default", is_set: true, value: "m" },
    { key: "registration_mode", group: "registration", label: "Sign-up mode", secret: false, source: "default", is_set: false, value: "", choices: ["closed", "invite", "open"] },
  ],
};

describe("instance setup screen (#220)", () => {
  it("never shows a saved secret and locks .env values", async () => {
    api.setup.config.mockResolvedValueOnce(CONFIG);
    render(<SetupPage />);
    const key = await screen.findByLabelText(/API key/);
    expect(key).toHaveValue("");
    expect(key).toHaveAttribute("type", "password");
    expect(screen.getByText("Saved. Leave blank to keep it.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Base URL/)).toBeDisabled();
  });

  it("saves only what changed and tests the typed key", async () => {
    api.setup.config.mockResolvedValueOnce(CONFIG);
    api.setup.save.mockResolvedValueOnce(CONFIG);
    api.setup.testLlm.mockResolvedValueOnce({ ok: true, message: "Connected: m answered." });
    render(<SetupPage />);
    await userEvent.type(await screen.findByLabelText(/API key/), "sk-new");
    await userEvent.click(screen.getByRole("button", { name: "Test the key" }));
    expect(api.setup.testLlm).toHaveBeenCalledWith({ api_key: "sk-new", base_url: undefined, model: undefined });
    expect(await screen.findByText("Connected: m answered.")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
    expect(api.setup.save).toHaveBeenCalledWith({ llm_api_key: "sk-new" });
  });

  it("locks sign-ups from the screen", async () => {
    api.setup.config.mockResolvedValueOnce(CONFIG);
    api.setup.save.mockResolvedValueOnce(CONFIG);
    render(<SetupPage />);
    await userEvent.selectOptions(await screen.findByLabelText("Sign-up mode"), "closed");
    await userEvent.click(screen.getAllByRole("button", { name: "Save" })[2]);
    expect(api.setup.save).toHaveBeenCalledWith({ registration_mode: "closed" });
  });
});
