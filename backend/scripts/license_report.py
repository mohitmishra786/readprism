"""Generate docs/licenses.md — the machine-generated dependency license report.

RL-08 / #260. Backend: `pip-licenses` over the installed environment (pip
install -r requirements.txt first). Frontend: `license-checker` via npx when
Node is available. Read-only by default (prints a summary); `--write` (re)writes
docs/licenses.md; `--check` additionally fails when a strong-copyleft license
appears (GPL/AGPL/EUPL/CDDL) — that is what the CI job runs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DOCS = REPO_ROOT / "docs" if (REPO_ROOT / "docs").is_dir() else BACKEND_DIR / "docs"
TARGET = DOCS / "licenses.md"
SELF_PACKAGES = {"weirling-backend", "weirling-frontend"}

# Licenses that redistribute obligations the project cannot accept by default
# (the project ships MIT). Weak copyleft (LGPL/MPL) is listed for review, not
# flagged: both are linkable without infecting the whole work.
STRONG_COPYLEFT = ("GPL", "AGPL", "EUPL", "CDDL")
WEAK_COPYLEFT = ("LGPL", "MPL")


def _normalize(license_name: str) -> str:
    return license_name.upper().replace("LICENSE", "")


def backend_licenses() -> list[dict]:
    try:
        from piplicenses import create_parser, get_packages

        args = create_parser().parse_args([])
        rows = list(get_packages(args))
        out = []
        for r in rows:
            # pip-licenses 5.x: metadata sometimes carries the full license
            # text instead of the short name (e.g. numpy), or UNKNOWN when the
            # metadata License field is empty — fall back to the PEP 639
            # license expression, then the trove classifier.
            license_name = r.get("license") or "UNKNOWN"
            if license_name in ("UNKNOWN", "") or len(license_name) > 100 or "\n" in license_name:
                license_name = (
                    r.get("license_expression")
                    if r.get("license_expression") not in (None, "UNKNOWN", "")
                    else license_name
                )
            if license_name in ("UNKNOWN", "") or len(license_name) > 100 or "\n" in license_name:
                classifiers = r.get("license_classifier") or []
                license_name = classifiers[0] if classifiers else "UNKNOWN (classifier)"
            out.append(
                {
                    "Name": r.get("name"),
                    "Version": r.get("version"),
                    "License": license_name,
                }
            )
        return out
    except ImportError:
        sys.exit(
            "pip-licenses is not installed in this environment. Run "
            "`pip install -r requirements.txt` (it includes pip-licenses) "
            "or `pip install pip-licenses`."
        )


def _npm_name(spec: str) -> str:
    """`name@version` or `@scope/name@version` → package name."""
    if spec.startswith("@"):
        body = spec[1:]
        return "@" + body.rsplit("@", 1)[0]
    return spec.rsplit("@", 1)[0]


def frontend_licenses() -> list[dict]:
    try:
        proc = subprocess.run(
            ["npx", "--yes", "license-checker", "--production", "--json"],
            cwd=REPO_ROOT / "frontend",
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    data = json.loads(proc.stdout)
    return sorted(
        (
            {
                "Name": _npm_name(name),
                "Version": info.get("version", "?"),
                "License": info.get("licenses", "?"),
            }
            for name, info in data.items()
        ),
        key=lambda row: row["Name"].lower(),
    )


def _flag_for(license_name: str) -> str | None:
    text = _normalize(license_name)
    # Check weak copyleft first: "LGPL" contains "GPL" as a substring.
    if "LGPL" in text or "MPL" in text:
        return "review"
    if "GPL" in text or any(tag in text for tag in ("EUPL", "CDDL")):
        return "strong-copyleft"
    return None


def render(backend: list[dict], frontend: list[dict]) -> tuple[str, list[str], list[str]]:
    lines = [
        "# Dependency licenses",
        "",
        "Machine-generated report (#260, RL-08) — do not edit by hand.",
        "Regenerate with `make licenses` (or `python backend/scripts/license_report.py --write`).",
        "",
        "Weirling is MIT-licensed. Redistribution obligations come from bundled",
        "dependencies; the tables below cover every installed backend package and",
        "every production frontend package.",
        "",
        "## Flagged and review-listed licenses",
        "",
        "| Package | License | Flag |",
        "|---|---|---|",
    ]
    flagged: list[str] = []
    review: list[str] = []
    for row in backend + frontend:
        flag = _flag_for(row["License"])
        if flag == "strong-copyleft":
            flagged.append(f"{row['Name']} ({row['License']})")
        elif flag == "review":
            review.append(row["Name"])
    for row in backend + frontend:
        flag = _flag_for(row["License"])
        if flag:
            lines.append(f"| {row['Name']} | {row['License']} | {flag} |")
    if not flagged and not review:
        lines.append("| (none) | — | — |")

    lines += [
        "",
        "## Backend (Python) — pip",
        "",
        "| Package | Version | License |",
        "|---|---|---|",
    ]
    for row in sorted(backend, key=lambda r: r["Name"].lower()):
        if row["Name"] in SELF_PACKAGES:
            continue
        lines.append(f"| {row['Name']} | {row['Version']} | {row['License']} |")

    if frontend:
        lines += [
            "",
            "## Frontend (npm) — production",
            "",
            "| Package | Version | License |",
            "|---|---|---|",
        ]
        for row in frontend:
            if row["Name"] in SELF_PACKAGES:
                continue
            lines.append(f"| {row['Name']} | {row['Version']} | {row['License']} |")

    lines += [
        "",
        "## Notes",
        "",
        "- `pip-licenses` reports the licenses as declared in package metadata;",
        "  counts by family: "
        + ", ".join(f"{k} ×{v}" for k, v in Counter(r["License"] for r in backend).most_common(6)),
        "",
    ]
    return "\n".join(lines) + "\n", flagged, review


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate docs/licenses.md")
    parser.add_argument("--write", action="store_true", help="Write docs/licenses.md")
    parser.add_argument(
        "--check", action="store_true", help="Exit 1 when a strong-copyleft license is present"
    )
    args = parser.parse_args()

    backend = backend_licenses()
    frontend = frontend_licenses()
    output, flagged, review = render(backend, frontend)

    if not args.write:
        print(
            f"backend={len(backend)} frontend={len(frontend)} "
            f"strong-copyleft={len(flagged)} review={len(review)} (run with --write to update docs/licenses.md)"
        )
    else:
        DOCS.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(output, encoding="utf-8")
        print(f"Wrote {TARGET}")

    if flagged:
        print("STRONG COPYLEFT: " + ", ".join(flagged), file=sys.stderr)
    if review:
        print("Review-listed (weak copyleft): " + ", ".join(review), file=sys.stderr)
    if args.check and flagged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
