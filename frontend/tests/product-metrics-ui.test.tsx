// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  digest: { top5: vi.fn(() => Promise.resolve({ status: "recorded" })) },
  metrics: { product: vi.fn() },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { Top5Question } from "../src/components/digest/Top5Question";
import ProductMetricsPage from "../src/app/(app)/admin/metrics/page";

describe("product metrics (#131)", () => {
  it("asks how many of the top 5 were wanted, once", async () => {
    render(<Top5Question digestId="d1" />);
    await userEvent.click(screen.getByRole("button", { name: "3" }));
    expect(api.digest.top5).toHaveBeenCalledWith("d1", 3);
    expect(screen.getByRole("status")).toHaveTextContent("Thanks");
    expect(screen.queryByRole("button", { name: "3" })).toBeNull();
  });

  it("shows the North Star and input metrics with their targets", async () => {
    api.metrics.product.mockResolvedValueOnce({
      enabled: true,
      now: {
        weekly_satisfied_readers: 7,
        ttfgd_minutes_median: 8.5,
        interleaving_win_rate: 0.58,
        retention_d7: 0.62,
        retention_d30: null,
        top5_wanted_median: 3,
        feed_health: 0.97,
      },
      targets: { retention_d7: ">= 0.60", feed_health: ">= 0.95" },
      events_last_30_days: { signup: 12, digest_opened: 40 },
      series: {},
    });
    render(<ProductMetricsPage />);
    expect(await screen.findByTestId("metric-weekly_satisfied_readers")).toHaveTextContent("7");
    expect(screen.getByTestId("metric-retention_d7")).toHaveTextContent("62%");
    expect(screen.getByTestId("metric-retention_d7")).toHaveTextContent("Target >= 0.60");
    expect(screen.getByTestId("metric-retention_d30")).toHaveTextContent("No data yet");
    expect(screen.getByText("digest opened")).toBeInTheDocument();
  });
});
