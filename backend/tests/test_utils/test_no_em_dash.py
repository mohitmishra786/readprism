"""Guard test to prevent em dashes (—) and en dashes (–) in user-facing copy.

Checks:
1. All STRING tokens in backend/app/**/*.py (excluding first-statement docstrings and comments).
2. All demo json files in backend/app/data/demo/*.json and OPML starter packs in backend/app/data/starter_packs/*.opml.
3. README.md and docs/**/*.md (excluding history files) outside fenced code blocks.
"""

import ast
import io
import tokenize
from pathlib import Path

# backend/ (the container's /app): app strings are checked everywhere. README
# and docs are repo-level and only exist outside the container, so that test
# skips there and runs in CI's "Config checks" job.
BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"


def _get_docstring_positions(source_text: str) -> set[tuple[int, int]]:
    """Return (lineno, col_offset) for all module, class, and function docstrings."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return set()

    positions: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.body and isinstance(node.body[0], ast.Expr):
                val = node.body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    positions.add((node.body[0].lineno, node.body[0].col_offset))
    return positions


def test_no_em_or_en_dash_in_backend_app_strings():
    """Ensure no user-facing string literals in backend/app contain em or en dashes."""
    offenders: list[str] = []

    for py_file in sorted(APP_DIR.rglob("*.py")):
        content = py_file.read_bytes()
        source_text = content.decode("utf-8", errors="replace")
        doc_positions = _get_docstring_positions(source_text)

        tokens = list(tokenize.tokenize(io.BytesIO(content).readline))
        for tok in tokens:
            if tok.type == tokenize.STRING:
                lineno, col = tok.start
                if (lineno, col) in doc_positions:
                    continue
                if "—" in tok.string or "–" in tok.string:
                    rel_path = py_file.relative_to(BACKEND_DIR)
                    offenders.append(f"{rel_path}:{lineno}: {tok.string.strip()[:80]}")

    assert offenders == [], "Found em/en dashes in backend/app strings:\n" + "\n".join(offenders)


def test_no_em_or_en_dash_in_app_data():
    """Ensure starter packs and demo data have zero em or en dashes."""
    offenders: list[str] = []

    for pattern in ("data/demo/*.json", "data/starter_packs/*.opml"):
        for data_file in sorted(APP_DIR.glob(pattern)):
            content = data_file.read_text(encoding="utf-8")
            if "—" in content or "–" in content:
                rel_path = data_file.relative_to(BACKEND_DIR)
                offenders.append(str(rel_path))

    assert offenders == [], "Found em/en dashes in app data files:\n" + "\n".join(offenders)


def test_app_dir_is_found():
    """Guard against a vacuous pass: the scans above must see real files."""
    assert len(list(APP_DIR.rglob("*.py"))) > 50
    assert list(APP_DIR.glob("data/starter_packs/*.opml"))


def test_no_em_or_en_dash_in_readme_and_docs():
    """Ensure README and non-history docs have zero em or en dashes outside fenced code blocks."""
    from tests.repo_files import require_repo_root

    REPO_ROOT = require_repo_root()
    excluded_exact = {
        "docs/PROGRESS.md",
        "docs/ROADMAP.md",
        "docs/releases/v0.2.0.md",
        "docs/licenses.md",
    }
    offenders: list[str] = []

    doc_files = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md"))]

    for doc_file in doc_files:
        rel_posix = doc_file.relative_to(REPO_ROOT).as_posix()
        if rel_posix in excluded_exact or rel_posix.startswith("docs/archive/"):
            continue

        lines = doc_file.read_text(encoding="utf-8").splitlines()
        in_code_block = False
        for idx, line in enumerate(lines, 1):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block and ("—" in line or "–" in line):
                offenders.append(f"{rel_posix}:{idx}: {line.strip()[:80]}")

    assert offenders == [], "Found em/en dashes in docs/README:\n" + "\n".join(offenders)
