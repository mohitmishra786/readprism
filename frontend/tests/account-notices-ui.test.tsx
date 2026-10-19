// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ auth: { me: vi.fn(), resendVerification: vi.fn(() => Promise.resolve({})) } }));
vi.mock("../src/lib/api", () => ({ api }));

import { AccountNotices } from "../src/components/AccountNotices";

describe("AccountNotices", () => {
  it("asks unverified users to confirm and can resend the link", async () => {
    api.auth.me.mockResolvedValue({ email: "r@example.com", email_verified: false, fetch_paused_until: null });
    render(<AccountNotices />);
    expect(await screen.findByText("r@example.com")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Resend the link" }));
    expect(api.auth.resendVerification).toHaveBeenCalled();
    expect(await screen.findByText("Sent. Check your inbox.")).toBeInTheDocument();
  });

  it("explains a paused fetch budget", async () => {
    const until = new Date(Date.now() + 3600_000).toISOString();
    api.auth.me.mockResolvedValue({ email: "r@example.com", email_verified: true, fetch_paused_until: until });
    render(<AccountNotices />);
    expect(await screen.findByText(/Feed fetching is paused/)).toBeInTheDocument();
  });

  it("stays silent for a verified, unpaused account", async () => {
    api.auth.me.mockResolvedValue({ email: "r@example.com", email_verified: true, fetch_paused_until: null });
    const { container } = render(<AccountNotices />);
    await new Promise((r) => setTimeout(r, 0));
    expect(container).toBeEmptyDOMElement();
  });
});
