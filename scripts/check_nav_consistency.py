"""
check_nav_consistency.py — Verify every published HTML page has the
canonical top-level navigation.

Why this exists
---------------
The nav bar lives in multiple places: four Jinja templates under
`frontend/` and the hand-written standalone About page at
`docs/about/index.html`. When a new standalone page is added (or a
template is edited), it's easy for the top-level nav items to drift
— e.g. the About page was first published missing the Topics dropdown
entirely. This script catches that before deploy.

What it checks
--------------
For every HTML file under `docs/`, it verifies the first `<nav class="cc-nav">`
block contains all of these top-level items:

  1. A "Home" link (`<a href="/">Home</a>` — also accepts `class="active"`)
  2. A Topics dropdown button (`>Topics<`)
  3. A Resources dropdown button (`>Resources<`)

"Daily Digest" is permitted but not required — homepage and digest
omit it; archive/daily/about pages include it.

Usage
-----
    cd christiancurator
    python scripts/check_nav_consistency.py
    # exit code 0  → all pages pass
    # exit code 1  → one or more pages are missing required items

Optional flag:
    --only-standalone    Check only pages that aren't generated from
                         templates (currently just /about/).

The script is read-only; it never modifies files.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

# ── Required top-level nav items ─────────────────────────────────────
# Each entry: (label, regex that must match inside the cc-nav block)
REQUIRED = [
    ("Home link",         re.compile(r'<a\s+href="/"[^>]*>\s*Home\s*</a>', re.I)),
    ("Topics dropdown",   re.compile(r'<button[^>]*>\s*Topics\s*</button>', re.I)),
    ("Resources dropdown", re.compile(r'<button[^>]*>\s*Resources\s*</button>', re.I)),
]

# Pages that are standalone / hand-written (not generated from a Jinja template).
# Drift here is the highest-risk class of drift.
STANDALONE_PAGES = {
    "about/index.html",
}

# Pull out the first <nav class="cc-nav"> ... </nav> block on the page.
NAV_BLOCK_RE = re.compile(
    r'<nav\s+class="cc-nav"[^>]*>([\s\S]*?)</nav>',
    re.I,
)


def extract_nav_block(html: str) -> str | None:
    m = NAV_BLOCK_RE.search(html)
    return m.group(1) if m else None


def check_file(path: Path) -> list[str]:
    """Return a list of missing-item descriptions, or [] if OK."""
    try:
        html = path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"READ ERROR: {e}"]

    nav = extract_nav_block(html)
    if nav is None:
        # Pages without any .cc-nav block are excluded (e.g. some utility
        # pages, or HTML fragments that aren't full site pages).
        return []

    missing = []
    for label, pattern in REQUIRED:
        if not pattern.search(nav):
            missing.append(label)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only-standalone",
        action="store_true",
        help="Check only hand-written standalone pages (highest drift risk).",
    )
    args = parser.parse_args()

    if args.only_standalone:
        candidates = [DOCS / rel for rel in STANDALONE_PAGES]
    else:
        candidates = sorted(DOCS.rglob("*.html"))

    failures: list[tuple[Path, list[str]]] = []
    checked = 0
    for p in candidates:
        if not p.exists():
            continue
        missing = check_file(p)
        checked += 1
        if missing:
            failures.append((p, missing))

    if failures:
        print(f"❌  Nav consistency check FAILED — {len(failures)} page(s) missing required nav items:\n")
        for path, missing in failures:
            rel = path.relative_to(REPO_ROOT)
            print(f"  {rel}")
            for item in missing:
                print(f"      – missing: {item}")
        print()
        print("Fix: ensure the <nav class=\"cc-nav\"> block on each page includes Home, Topics, and Resources.")
        print("Reference: frontend/archive_template.html has the canonical pattern.")
        return 1

    print(f"✅  Nav consistency OK — checked {checked} page(s), all pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
