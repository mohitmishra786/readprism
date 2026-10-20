// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  auth: { me: vi.fn(() => Promise.resolve({ email: "o@example.com", email_verified: true })) },
  metrics: { instanceHealth: vi.fn() },
  billing: { state: vi.fn(() => Promise.resolve({ plan: "selfhost" })) },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { AccountNotices } from "../src/components/AccountNotices";

describe("instance health banner (#234)", () => {
  it("lists problems for the owner", async () => {
    api.metrics.instanceHealth.mockResolvedValueOnce({
      owner: true,
      problems: [
        { key: "worker:scrape", message: "The scrape worker hasn't processed jobs for 45 minutes.", hint: "Check the worker-scrape container and its logs." },
      ],
    });
    render(<AccountNotices />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This Weirling instance needs attention");
    expect(alert).toHaveTextContent("The scrape worker hasn't processed jobs for 45 minutes.");
  });

  it("shows nothing when healthy or not the owner", async () => {
    api.metrics.instanceHealth.mockResolvedValueOnce({ owner: false, problems: [] });
    render(<AccountNotices />);
    await Promise.resolve();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
