// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RegisterPage from "../src/app/(auth)/register/page";

const registrationMock = vi.hoisted(() => vi.fn());
const registerMock = vi.hoisted(() => vi.fn());
vi.mock("../src/lib/api", () => ({
  api: {
    auth: {
      registration: registrationMock,
      register: registerMock,
    },
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

describe("Registration terms consent checkbox (#181)", () => {
  it("renders required consent checkbox only when hosted is true", async () => {
    registrationMock.mockResolvedValueOnce({
      mode: "open",
      open: true,
      invite_required: false,
      first_account: false,
      hosted: true,
    });
    render(<RegisterPage />);

    const checkbox = await screen.findByRole("checkbox", {
      name: /I agree to the Terms and the Privacy policy/i,
    });
    expect(checkbox).toBeInTheDocument();
    expect(checkbox).toBeRequired();

    const termsLink = screen.getByRole("link", { name: "Terms" });
    expect(termsLink).toHaveAttribute("href", "/terms");
    const privacyLink = screen.getByRole("link", { name: "Privacy policy" });
    expect(privacyLink).toHaveAttribute("href", "/privacy");
  });

  it("does not render consent checkbox on self-host", async () => {
    registrationMock.mockResolvedValueOnce({
      mode: "open",
      open: true,
      invite_required: false,
      first_account: false,
      hosted: false,
    });
    render(<RegisterPage />);

    await screen.findByRole("button", { name: /create account/i });
    expect(
      screen.queryByRole("checkbox", {
        name: /I agree to the Terms and the Privacy policy/i,
      })
    ).toBeNull();
  });
});
