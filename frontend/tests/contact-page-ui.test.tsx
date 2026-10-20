// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const getContactInfoMock = vi.fn();
vi.mock("../src/lib/api", () => ({
  getContactInfo: () => getContactInfoMock(),
}));

import ContactPage from "../src/app/contact/page";

describe("Contact page (#183)", () => {
  it("shows takedown section when GRIEVANCE_CONTACT_EMAIL is set", async () => {
    getContactInfoMock.mockResolvedValueOnce({
      grievance_contact_email: "grievance@example.com",
    });
    render(<ContactPage />);
    expect(await screen.findByText("Takedown and grievance requests")).toBeInTheDocument();
    expect(screen.getByText("grievance@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Template: not legal advice/)).toBeInTheDocument();
  });

  it("hides takedown section when GRIEVANCE_CONTACT_EMAIL is empty", async () => {
    getContactInfoMock.mockResolvedValueOnce({
      grievance_contact_email: null,
    });
    render(<ContactPage />);
    await Promise.resolve();
    expect(screen.queryByText("Takedown and grievance requests")).not.toBeInTheDocument();
  });
});
