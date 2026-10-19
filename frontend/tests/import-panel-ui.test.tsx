// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  sources: {
    importFeeds: vi.fn(),
    importSaved: vi.fn(),
    importJob: vi.fn(),
  },
}));
vi.mock("../src/lib/api", () => ({ api }));

import { ImportPanel } from "../src/components/onboarding/ImportPanel";

const file = (name: string) => new File(["x"], name);

describe("ImportPanel (#150, #202)", () => {
  it("routes OPML to feeds and Pocket/CSV to saved articles, then summarises", async () => {
    api.sources.importFeeds.mockResolvedValue({ created: 41, queued: false, errors: [] });
    api.sources.importSaved.mockResolvedValue({ created: 120, errors: [] });
    const onImported = vi.fn();
    render(<ImportPanel onImported={onImported} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, [file("feedly.opml"), file("ril_export.html")]);
    expect(await screen.findByText("Imported 41 feeds, 120 saved articles.")).toBeInTheDocument();
    expect(api.sources.importFeeds).toHaveBeenCalledTimes(1);
    expect(api.sources.importSaved).toHaveBeenCalledTimes(1);
    expect(onImported).toHaveBeenCalledWith(41, 120);
  });

  it("lists skipped rows without failing the import", async () => {
    api.sources.importSaved.mockResolvedValue({
      created: 2,
      errors: [{ row: 2, url: "javascript:alert(1)", error: "not an http(s) URL" }],
    });
    render(<ImportPanel />);
    await userEvent.upload(document.querySelector("input[type=file]") as HTMLInputElement, file("export.csv"));
    expect(await screen.findByText("1 row skipped")).toBeInTheDocument();
    expect(screen.getByText(/Imported 2 saved articles/)).toBeInTheDocument();
  });

  it("follows a queued background import to completion", async () => {
    api.sources.importFeeds.mockResolvedValue({ created: 0, queued: true, job_id: "j1", errors: [] });
    api.sources.importJob.mockResolvedValue({ status: "done", total: 2000, done: 2000, created: 2000, progress: 1 });
    render(<ImportPanel />);
    await userEvent.upload(document.querySelector("input[type=file]") as HTMLInputElement, file("big.opml"));
    expect(await screen.findByText("Imported 2000 feeds.")).toBeInTheDocument();
    expect(api.sources.importJob).toHaveBeenCalledWith("j1");
  });

  it("reports a file that fails outright", async () => {
    api.sources.importFeeds.mockRejectedValue(new Error("Invalid OPML"));
    render(<ImportPanel />);
    await userEvent.upload(document.querySelector("input[type=file]") as HTMLInputElement, file("bad.opml"));
    expect(await screen.findByText("bad.opml: Invalid OPML")).toBeInTheDocument();
  });
});
