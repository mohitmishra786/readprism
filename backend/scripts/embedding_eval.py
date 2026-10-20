"""Compare embedding models on real, openly licensed articles (#203).

Dataset: the 52 articles in tests/fixtures/real_pages (Go blog BSD-3-Clause,
Rust blog MIT/Apache-2.0, Kubernetes blog CC BY 4.0, Wikipedia CC BY-SA 4.0;
licenses per article in manifest.json).

Tasks, all scored per model:
- title -> article: the page title as a query, all 52 bodies as the corpus
  (MRR and recall@1). Like searching your archive by a remembered headline.
- summary -> article: the LLM brief from docs/eval/summary-models.jsonl (a
  paraphrase written by another model) as the query. Harder: no shared title.
- neighbours: for each body, how many of its 5 nearest other bodies come from
  the same source (Go, Rust, Kubernetes, Wikipedia). A proxy for "more like
  this" and interest matching.
Plus encode speed on this machine's CPU and vector size.

Run from backend/:
    python scripts/embedding_eval.py --out ../docs/eval/embedding-models.md
Downloads model weights on first run (MiniLM ~90 MB, bge-small ~130 MB,
Nomic ~550 MB, bge-m3 ~2.3 GB).
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import time
from pathlib import Path

import numpy as np

PAGES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "real_pages"
SUMMARIES = Path(__file__).resolve().parents[2] / "docs" / "eval" / "summary-models.jsonl"

MODELS = [
    # name, query prefix, document prefix, note
    ("sentence-transformers/all-MiniLM-L6-v2", "", "", "current default"),
    (
        "BAAI/bge-small-en-v1.5",
        "Represent this sentence for searching relevant passages: ",
        "",
        "same 384-d column",
    ),
    ("nomic-ai/nomic-embed-text-v1.5", "search_query: ", "search_document: ", "768-d, 8k context"),
    ("BAAI/bge-m3", "", "", "1024-d, 8k context, multilingual"),
]


def load_articles(summaries: Path = SUMMARIES) -> list[dict]:
    manifest = json.loads((PAGES / "manifest.json").read_text())
    rows = []
    for row in manifest:
        body = gzip.decompress((PAGES / f"{row['id']}.txt.gz").read_bytes()).decode()
        page = gzip.decompress((PAGES / f"{row['id']}.html.gz").read_bytes()).decode(
            "utf-8", "ignore"
        )
        match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        title = html.unescape(match.group(1)).strip() if match else ""
        # Drop site suffixes ("| Rust Blog", "- Wikipedia") so the title isn't a
        # giveaway for the source in the neighbour task.
        title = re.split(r"\s+[|\-\u2013\u2014]\s+(?=[^|\-\u2013\u2014]*$)", title)[0].strip()
        rows.append({**row, "title": title, "body": " ".join(body.split())})
    briefs = {}
    if summaries.exists():
        for line in summaries.read_text().splitlines():
            r = json.loads(line)
            brief = (r.get("large") or {}).get("brief") or (r.get("fast") or {}).get("brief")
            if brief:
                briefs[r["id"]] = brief
    for row in rows:
        row["brief"] = briefs.get(row["id"], "")
    return rows


def mrr_and_r1(queries: np.ndarray, docs: np.ndarray, targets: list[int]) -> tuple[float, float]:
    scores = queries @ docs.T
    rr, hits = [], 0
    for qi, target in enumerate(targets):
        order = np.argsort(-scores[qi])
        rank = int(np.where(order == target)[0][0]) + 1
        rr.append(1.0 / rank)
        hits += rank == 1
    return float(np.mean(rr)), hits / len(targets)


def neighbour_precision(docs: np.ndarray, labels: list[str], k: int = 5) -> float:
    sims = docs @ docs.T
    np.fill_diagonal(sims, -np.inf)
    total = 0.0
    for i, label in enumerate(labels):
        nearest = np.argsort(-sims[i])[:k]
        total += sum(labels[j] == label for j in nearest) / k
    return total / len(labels)


def _patch_legacy_attention_mask(model) -> None:
    """Nomic's remote code calls PreTrainedModel.get_extended_attention_mask,
    which transformers 5 removed. Restore the old behaviour for this run only
    (#244 has to solve the same thing before Nomic can ship)."""
    import torch

    inner = getattr(model[0], "auto_model", None)
    if inner is None or hasattr(inner, "get_extended_attention_mask"):
        return

    def get_extended_attention_mask(self, attention_mask, input_shape, *args, **kwargs):
        mask = (
            attention_mask[:, None, None, :]
            if attention_mask.dim() == 2
            else attention_mask[:, None]
        )
        mask = mask.to(dtype=self.dtype)
        return (1.0 - mask) * torch.finfo(self.dtype).min

    for cls in type(inner).__mro__:
        if cls.__module__.startswith("transformers_modules"):
            cls.get_extended_attention_mask = get_extended_attention_mask
    type(inner).get_extended_attention_mask = get_extended_attention_mask


def evaluate(model_name: str, qp: str, dp: str, rows: list[dict]) -> dict:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, trust_remote_code=True, device="cpu")
    _patch_legacy_attention_mask(model)
    bodies = [dp + r["body"] for r in rows]
    started = time.perf_counter()
    docs = model.encode(bodies, normalize_embeddings=True, batch_size=4)
    seconds = time.perf_counter() - started
    titles = model.encode([qp + r["title"] for r in rows], normalize_embeddings=True)
    title_mrr, title_r1 = mrr_and_r1(titles, docs, list(range(len(rows))))
    with_brief = [i for i, r in enumerate(rows) if r["brief"]]
    briefs = model.encode([qp + rows[i]["brief"] for i in with_brief], normalize_embeddings=True)
    brief_mrr, brief_r1 = mrr_and_r1(briefs, docs, with_brief)
    return {
        "model": model_name,
        "dim": int(docs.shape[1]),
        "max_tokens": int(getattr(model, "max_seq_length", 0) or 0),
        "title_mrr": title_mrr,
        "title_r1": title_r1,
        "brief_mrr": brief_mrr,
        "brief_r1": brief_r1,
        "brief_n": len(with_brief),
        "neighbours_p5": neighbour_precision(docs, [r["source"] for r in rows]),
        "docs_per_second": len(rows) / seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", nargs="*", help="subset of model names")
    parser.add_argument("--summaries", type=Path, default=SUMMARIES)
    args = parser.parse_args()
    rows = load_articles(args.summaries)
    results = []
    for name, qp, dp, note in MODELS:
        if args.models and name not in args.models:
            continue
        print(f"evaluating {name}...", flush=True)
        result = evaluate(name, qp, dp, rows)
        result["note"] = note
        results.append(result)
        print(json.dumps(result), flush=True)
    lines = [
        "# Embedding models on real articles (#203)",
        "",
        f"{len(rows)} openly licensed articles from `backend/tests/fixtures/real_pages` "
        "(13 each from the Go blog, Rust blog, Kubernetes blog and Wikipedia; licenses per "
        "article in `manifest.json`). Generated by `backend/scripts/embedding_eval.py` on "
        f"{time.strftime('%Y-%m-%d')}, CPU only.",
        "",
        "| Model | Dim | Max tokens | Title to article MRR (R@1) | Summary to article MRR (R@1) "
        "| Same-source neighbours P@5 | Docs/s | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r['model'].split('/')[-1]}` | {r['dim']} | {r['max_tokens']} "
            f"| {r['title_mrr']:.3f} ({r['title_r1']:.2f}) "
            f"| {r['brief_mrr']:.3f} ({r['brief_r1']:.2f}, n={r['brief_n']}) "
            f"| {r['neighbours_p5']:.3f} | {r['docs_per_second']:.1f} | {r['note']} |"
        )
    lines += [
        "",
        "- **Title to article:** the page title is the query; all article bodies are the corpus.",
        "- **Summary to article:** an LLM-written brief of the article is the query (no shared title).",
        "- **Neighbours P@5:** share of each article's 5 nearest articles from the same source.",
        "- **Docs/s:** encoding speed of full article bodies on this machine's CPU.",
    ]
    args.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
