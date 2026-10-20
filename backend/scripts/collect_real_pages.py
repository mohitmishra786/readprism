#!/usr/bin/env python
"""Collect the real-page extraction fixtures (#230).

The generated golden corpus (app/services/ingestion/golden.py) tests the
generator as much as the extractor. These fixtures are real published pages
whose ground-truth text comes from the same post's Markdown source in a
public, permissively licensed repository, so nothing is hand-labelled:

- Go blog          go.dev/blog            golang/website       BSD-3-Clause
- Rust blog        blog.rust-lang.org     rust-lang/blog...    MIT OR Apache-2.0
- Kubernetes blog  kubernetes.io/blog     kubernetes/website   CC BY 4.0
- Wikipedia        en.wikipedia.org/wiki  plain-text API       CC BY-SA 4.0

Run once (needs network and `gh` for GitHub API listings); the output is
committed under tests/fixtures/real_pages with a manifest recording each
page's URL, source, licence and fetch date:

    cd backend && python scripts/collect_real_pages.py --per-source 13
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "real_pages"
UA = "Weirling-fixture-collector/1.0 (+https://github.com/mohitmishra786/weirling)"

LICENSES = {
    "go": ("BSD-3-Clause", "https://github.com/golang/website/blob/master/LICENSE"),
    "rust": ("MIT OR Apache-2.0", "https://github.com/rust-lang/blog.rust-lang.org"),
    "kubernetes": ("CC BY 4.0", "https://github.com/kubernetes/website/blob/main/LICENSE"),
    "wikipedia": ("CC BY-SA 4.0", "https://en.wikipedia.org/wiki/Wikipedia:Copyrights"),
}

WIKIPEDIA = [
    "Garbage_collection_(computer_science)",
    "B-tree",
    "Just-in-time_compilation",
    "Transport_Layer_Security",
    "Raft_(algorithm)",
    "Bloom_filter",
    "Unicode",
    "Write-ahead_logging",
    "Vector_database",
    "Content_delivery_network",
    "Rust_(programming_language)",
    "PostgreSQL",
    "WebAssembly",
]


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def gh(path: str, jq: str | None = None) -> str:
    args = ["gh", "api", path] + (["--jq", jq] if jq else [])
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def gh_file(repo: str, path: str) -> str:
    return base64.b64decode(gh(f"repos/{repo}/contents/{path}", ".content")).decode("utf-8")


def split_front_matter(text: str) -> tuple[str, str]:
    for fence in ("---", "+++"):
        if text.startswith(fence):
            end = text.find(f"\n{fence}", len(fence))
            if end != -1:
                return text[len(fence) : end], text[end + len(fence) + 1 :]
    return "", text


def markdown_to_text(md: str) -> str:
    """Plain text a reader sees: link text kept, URLs and markup dropped."""
    text = re.sub(r"\{\{.*?\}\}", " ", md, flags=re.S)  # Go/Hugo template calls
    text = re.sub(r"\{%.*?%\}", " ", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links -> text
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)  # reference links
    text = re.sub(r"^\s*\[[^\]]+\]:\s*\S+.*$", " ", text, flags=re.M)  # link defs
    text = re.sub(r"<[^>]+>", " ", text)  # inline HTML
    text = re.sub(r"^```.*$", " ", text, flags=re.M)  # fence lines (code kept)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"[*_`|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def go_posts(n: int) -> list[dict]:
    names = json.loads(gh("repos/golang/website/contents/_content/blog", "[.[] | .name]"))
    posts = sorted((x for x in names if x.endswith(".md")), reverse=True)[: n * 2]
    out = []
    for name in posts:
        _, body = split_front_matter(gh_file("golang/website", f"_content/blog/{name}"))
        slug = name[:-3]
        out.append({"source": "go", "url": f"https://go.dev/blog/{slug}", "md": body})
    return out


def rust_posts(n: int) -> list[dict]:
    names = json.loads(gh("repos/rust-lang/blog.rust-lang.org/contents/content", "[.[] | .name]"))
    out = []
    for name in sorted((x for x in names if x.endswith(".md")), reverse=True):
        front, body = split_front_matter(gh_file("rust-lang/blog.rust-lang.org", f"content/{name}"))
        m = re.search(r'^path\s*=\s*"([^"]+)"', front, re.M)
        if m:
            out.append(
                {"source": "rust", "url": f"https://blog.rust-lang.org/{m.group(1)}/", "md": body}
            )
        if len(out) >= n * 2:
            break
    return out


def kubernetes_posts(n: int) -> list[dict]:
    base = "content/en/blog/_posts"
    out = []
    for year in ("2026", "2025"):
        files = json.loads(
            gh(
                f"repos/kubernetes/website/contents/{base}/{year}",
                '[.[] | select(.name|endswith(".md")) | .path]',
            )
        )
        for path in files:
            front, body = split_front_matter(gh_file("kubernetes/website", path))
            date = re.search(r"^date:\s*(\d{4})-(\d{2})-(\d{2})", front, re.M)
            slug = re.search(r"^slug:\s*(\S+)", front, re.M)
            if date and slug and "draft: true" not in front:
                y, mth, d = date.groups()
                url = f"https://kubernetes.io/blog/{y}/{mth}/{d}/{slug.group(1)}/"
                out.append({"source": "kubernetes", "url": url, "md": body})
            if len(out) >= n * 2:
                return out
    return out


def wikipedia_pages(n: int) -> list[dict]:
    out = []
    for title in WIKIPEDIA[:n]:
        api = (
            "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
            f"&format=json&formatversion=2&titles={urllib.parse.quote(title)}"
        )
        extract = json.loads(http_get(api))["query"]["pages"][0]["extract"]
        # Drop the trailing reference sections, which the article page renders
        # as citation lists rather than prose.
        extract = re.split(
            r"\n== (See also|References|Notes|External links|Further reading) ==", extract
        )[0]
        text = re.sub(r"=+ ([^=]+) =+", r"\1", extract)
        out.append(
            {"source": "wikipedia", "url": f"https://en.wikipedia.org/wiki/{title}", "text": text}
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-source", type=int, default=13)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    today = datetime.now(UTC).date().isoformat()
    candidates = (
        go_posts(args.per_source)
        + rust_posts(args.per_source)
        + kubernetes_posts(args.per_source)
        + wikipedia_pages(args.per_source)
    )
    per_source: dict[str, int] = {}
    for item in candidates:
        src = item["source"]
        if per_source.get(src, 0) >= args.per_source:
            continue
        try:
            html = http_get(item["url"])
        except Exception as e:  # moved/unpublished post: skip it
            print(f"skip {item['url']}: {e}")
            continue
        expected = item.get("text") or markdown_to_text(item["md"])
        if len(expected.split()) < 150:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        page_id = f"{src}-{per_source[src]:02d}"
        (OUT / f"{page_id}.html.gz").write_bytes(gzip.compress(html.encode("utf-8"), mtime=0))
        (OUT / f"{page_id}.txt.gz").write_bytes(gzip.compress(expected.encode("utf-8"), mtime=0))
        licence, licence_url = LICENSES[src]
        manifest.append(
            {
                "id": page_id,
                "source": src,
                "url": item["url"],
                "license": licence,
                "license_url": licence_url,
                "fetched": today,
            }
        )
        print(f"{page_id} {item['url']} ({len(expected.split())} words)")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(per_source, len(manifest), "pages")


if __name__ == "__main__":
    main()
