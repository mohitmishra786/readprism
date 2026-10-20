// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace }) }));
const api = vi.hoisted(() => ({
  onboarding: {
    expandInterests: vi.fn(() => Promise.resolve({ topics: ["Rust", "PostgreSQL"] })),
    complete: vi.fn(() => Promise.resolve({ status: "ok" })),
    startFirstDigest: vi.fn(() => Promise.resolve({})),
    calibration: vi.fn(() => Promise.resolve([])),
    rateCalibration: vi.fn(),
  },
  sources: {
    starterPacks: vi.fn(() =>
      Promise.resolve([
        { id: "systems-programming", title: "Systems Programming", feed_count: 12, feeds: [], suggested: true, subscribed: 0 },
      ]),
    ),
    subscribePack: vi.fn(() => Promise.resolve({ status: "ok", subscribed: 12, already_had: 0 })),
    importFeeds: vi.fn(),
    importSaved: vi.fn(),
    importJob: vi.fn(),
    add: vi.fn(() => Promise.resolve({})),
  },
  newsletter: {
    address: vi.fn(() => Promise.resolve({ address: "u.abc@in.example.com", inbound_configured: false, email_verified: true })),
  },
  creators: { add: vi.fn() },
  preferences: { update: vi.fn(() => Promise.resolve({})) },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { OnboardingWizard } from "../src/components/onboarding/OnboardingWizard";

async function next() {
  await userEvent.click(screen.getByRole("button", { name: /Continue|Skip for now/ }));
}

describe("OnboardingWizard", () => {
  it("expands interests into editable topic chips", async () => {
    render(<OnboardingWizard />);
    await userEvent.type(screen.getByRole("textbox"), "rust, postgres internals");
    await next();
    expect(await screen.findByText("Rust")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove topic Rust" }));
    expect(screen.queryByText("Rust")).not.toBeInTheDocument();
  });

  it("asks for interests before continuing", async () => {
    render(<OnboardingWizard />);
    await next();
    expect(screen.getByText(/Tell us a little about what you read/)).toBeInTheDocument();
  });

  it("subscribes the selected starter packs when moving on (#152)", async () => {
    render(<OnboardingWizard />);
    await userEvent.type(screen.getByRole("textbox"), "rust");
    await next(); // -> Confirm Topics
    await screen.findByText("Rust");
    await next(); // -> Starter Packs
    expect(await screen.findByRole("button", { name: /Systems Programming/ })).toHaveAttribute("aria-pressed", "true");
    await next();
    expect(api.sources.subscribePack).toHaveBeenCalledWith("systems-programming");
    expect(await screen.findByText(/Coming from another reader/)).toBeInTheDocument();
  });

  it("walks through every step and saves the chosen time and email setting (#201)", async () => {
    render(<OnboardingWizard />);
    await userEvent.type(screen.getByRole("textbox"), "rust");
    await next(); // Confirm Topics
    await screen.findByText("Rust");
    for (const heading of ["Starter Packs", "Add Sources", "Newsletters", "Add Creators", "Rate Headlines", "Digest Preferences"]) {
      await next();
      expect(await screen.findByText(new RegExp(`: ${heading}$`))).toBeInTheDocument();
    }
    const time = screen.getByLabelText("Delivery time");
    await userEvent.clear(time);
    await userEvent.type(time, "06:30");
    await userEvent.click(screen.getByLabelText(/Email me the digest/));
    await userEvent.click(screen.getByRole("button", { name: "Start Weirling" }));

    expect(api.onboarding.complete).toHaveBeenCalledWith(
      expect.objectContaining({ confirmed_topics: ["Rust", "PostgreSQL"], sample_ratings: [] }),
    );
    expect(api.preferences.update).toHaveBeenCalledWith(
      expect.objectContaining({ digest_frequency: "in_app_only", digest_time_morning: "06:30:00" }),
    );
    expect(replace).toHaveBeenCalledWith("/digest");
  });
});
