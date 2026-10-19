// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  newsletter: { address: vi.fn(), sendTest: vi.fn(), testStatus: vi.fn() },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { NewsletterAddressCard } from "../src/components/NewsletterAddressCard";

describe("NewsletterAddressCard (#151)", () => {
  it("shows the address and explains when inbound mail isn't set up", async () => {
    api.newsletter.address.mockResolvedValue({ address: "u.abc@in.example.com", inbound_configured: false, email_verified: true });
    render(<NewsletterAddressCard />);
    expect(await screen.findByText("u.abc@in.example.com")).toBeInTheDocument();
    expect(screen.getByText(/aren't set up on this instance/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send a test" })).not.toBeInTheDocument();
  });

  it("warns unverified users that newsletters are held", async () => {
    api.newsletter.address.mockResolvedValue({ address: "u.abc@in.example.com", inbound_configured: true, email_verified: false });
    render(<NewsletterAddressCard />);
    expect(await screen.findByText(/Confirm your email first/)).toBeInTheDocument();
  });

  it("reports when the test email arrives", async () => {
    api.newsletter.address.mockResolvedValue({ address: "u.abc@in.example.com", inbound_configured: true, email_verified: true });
    api.newsletter.sendTest.mockResolvedValue({ status: "sent" });
    api.newsletter.testStatus.mockResolvedValue({
      status: "received",
      sent_at: "2026-10-20T10:00:00Z",
      received_at: "2026-10-20T10:00:09Z",
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<NewsletterAddressCard />);
    await user.click(await screen.findByRole("button", { name: "Send a test" }));
    await vi.advanceTimersByTimeAsync(3000); // one poll interval
    expect(await screen.findByText(/Received. Your address works. Arrived in 9 s./)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
