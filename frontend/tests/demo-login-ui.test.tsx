// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/login",
}));

const api = vi.hoisted(() => ({
  auth: {
    registration: vi.fn(),
    login: vi.fn(),
    demo: vi.fn(() => Promise.resolve({ access_token: "tok", expires_in: 1800 })),
    magicLinkRequest: vi.fn(),
    me: vi.fn(),
    resendVerification: vi.fn(() => Promise.resolve({})),
  },
  metrics: { instanceHealth: vi.fn(() => Promise.resolve({ problems: [] })) },
  billing: { state: vi.fn(() => Promise.resolve({ plan: "selfhost" })) },
}));
vi.mock("../src/lib/api", () => ({ api }));

import LoginPage from "../src/app/(auth)/login/page";
import { AccountNotices } from "../src/components/AccountNotices";

describe("Demo mode UI (#229)", () => {
  it("renders 'Try the demo' button when demo_mode is enabled", async () => {
    api.auth.registration.mockResolvedValue({
      mode: "closed",
      open: false,
      invite_required: false,
      demo_mode: true,
    });
    render(<LoginPage />);
    const btn = await screen.findByRole("button", { name: "Try the demo" });
    expect(btn).toBeInTheDocument();

    await userEvent.click(btn);
    expect(api.auth.demo).toHaveBeenCalled();
    expect(replaceMock).toHaveBeenCalledWith("/digest");
  });

  it("omits 'Try the demo' button when demo_mode is false", async () => {
    api.auth.registration.mockResolvedValue({
      mode: "open",
      open: true,
      invite_required: false,
      demo_mode: false,
    });
    render(<LoginPage />);
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Try the demo" })).toBeNull();
    });
  });

  it("shows demo notice in AccountNotices when user is the demo persona", async () => {
    api.auth.me.mockResolvedValue({
      email: "demo@readprism.local",
      email_verified: true,
      fetch_paused_until: null,
      is_demo: true,
    });
    render(<AccountNotices />);
    expect(
      await screen.findByText(/You are exploring the ReadPrism demo. It is read-only and resets nightly./)
    ).toBeInTheDocument();
  });
});
