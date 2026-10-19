// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const items = Array.from({ length: 8 }, (_, i) => ({
  id: `c${i}`,
  title: `Headline ${i}`,
  url: `https://www.site${i}.com/a`,
  topic_clusters: [`topic ${i}`],
  reading_time_minutes: 4,
}));
const api = vi.hoisted(() => ({
  onboarding: {
    calibration: vi.fn(),
    rateCalibration: vi.fn(() => Promise.resolve({ status: "ok", clusters_updated: 0, clusters_created: 1 })),
  },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { CalibrationStep } from "../src/components/onboarding/CalibrationStep";

describe("CalibrationStep (#149)", () => {
  it("shows 8 real headlines and sends each rating", async () => {
    api.onboarding.calibration.mockResolvedValue(items);
    render(<CalibrationStep />);
    expect(await screen.findByText("Headline 0")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByText("site3.com · topic 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More like Headline 2" }));
    await userEvent.click(screen.getByRole("button", { name: "Less like Headline 5" }));
    expect(api.onboarding.rateCalibration).toHaveBeenCalledWith("c2", 1);
    expect(api.onboarding.rateCalibration).toHaveBeenCalledWith("c5", -1);
    expect(screen.getByText(/2\/8 rated/)).toBeInTheDocument();
  });
});
