// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const downloadFile = vi.hoisted(() => vi.fn(() => Promise.resolve()));
vi.mock("../src/lib/api", () => ({ downloadFile }));

import { CitationExport } from "../src/components/CitationExport";

describe("citation export (#250)", () => {
  it("downloads BibTeX and RIS", async () => {
    render(<CitationExport />);
    await userEvent.click(screen.getByRole("button", { name: "BibTeX (.bib)" }));
    await userEvent.click(screen.getByRole("button", { name: "RIS (.ris)" }));
    expect(downloadFile).toHaveBeenCalledWith("/integrations/bibtex", "readprism-saved.bib");
    expect(downloadFile).toHaveBeenCalledWith("/integrations/ris", "readprism-saved.ris");
  });

  it("shows a failed download", async () => {
    downloadFile.mockRejectedValueOnce(new Error("Download failed (HTTP 500)"));
    render(<CitationExport />);
    await userEvent.click(screen.getByRole("button", { name: "BibTeX (.bib)" }));
    expect(await screen.findByText("Download failed (HTTP 500)")).toBeInTheDocument();
  });
});
