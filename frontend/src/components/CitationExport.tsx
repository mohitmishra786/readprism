"use client";
import { useState } from "react";
import { downloadFile } from "../lib/api";

const FORMATS = [
  { path: "/integrations/bibtex", file: "readprism-saved.bib", label: "BibTeX (.bib)" },
  { path: "/integrations/ris", file: "readprism-saved.ris", label: "RIS (.ris)" },
];

// Saved articles as citations for Zotero, Mendeley, EndNote, JabRef (#250).
export function CitationExport() {
  const [error, setError] = useState("");
  return (
    <div className="text-sm">
      <p className="text-stone-600 dark:text-stone-300">
        Download your saved articles as citations. arXiv papers become preprints with their arXiv id,
        DOI links become journal articles, everything else a web page.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {FORMATS.map((f) => (
          <button
            key={f.path}
            type="button"
            onClick={() => downloadFile(f.path, f.file).catch((e) => setError(e.message))}
            className="rounded border border-stone-300 px-3 py-1 dark:border-stone-600"
          >
            {f.label}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">
        In Zotero: File → Import… and choose the file.
      </p>
      {error && <p className="mt-2 text-red-600">{error}</p>}
    </div>
  );
}
