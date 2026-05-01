"""
backfill_nav.py — Inject canonical <nav class="cc-nav"> into pages
that pre-date the Topics + Resources dropdowns.

Targets:
  1. docs/archive/YYYY-MM-DD/index.html   (active = Archive)
  2. docs/archive/index.html              (active = Archive)
  3. docs/voices/<slug>/index.html        (active = Voices)

Two scenarios per file:
  A. Existing <nav class="cc-nav">…</nav> block — replace in place.
  B. No nav block at all — insert before </header>.

Usage:
    python scripts/backfill_nav.py
    python scripts/backfill_nav.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
TEMPLATE = REPO_ROOT / "frontend" / "archive_template.html"

NAV_RE = re.compile(
    r'<nav\s+class="cc-nav"[^>]*>.*?</nav>',
    re.IGNORECASE | re.DOTALL,
)
HEADER_END_RE = re.compile(r'</header>', re.IGNORECASE)


def extract_canonical_nav() -> str:
    src = TEMPLATE.read_text(encoding="utf-8")
    m = NAV_RE.search(src)
    if not m:
        sys.exit("ERROR: could not find <nav class='cc-nav'> in archive_template.html")
    return m.group(0)


def adjust_active(nav: str, page_kind: str) -> str:
    nav = re.sub(
        r'(<a\s+href="/(about|voices|archive)/")\s+class="active"',
        r'\1',
        nav,
    )
    if page_kind in ("archive", "archive_index"):
        nav = nav.replace(
            '<a href="/archive/">',
            '<a href="/archive/" class="active">',
            1,
        )
    elif page_kind == "voices":
        nav = nav.replace(
            '<a href="/voices/">',
            '<a href="/voices/" class="active">',
            1,
        )
    return nav


def discover_targets():
    targets = []
    for p in sorted((DOCS / "archive").glob("*/index.html")):
        if p.parent.name == "archive":
            continue
        targets.append((p, "archive"))

    archive_index = DOCS / "archive" / "index.html"
    if archive_index.exists():
        targets.append((archive_index, "archive_index"))

    voices_dir = DOCS / "voices"
    if voices_dir.exists():
        for p in sorted(voices_dir.glob("*/index.html")):
            targets.append((p, "voices"))

    return targets


def needs_backfill(html: str) -> bool:
    m = NAV_RE.search(html)
    if not m:
        return True
    block = m.group(0)
    has_topics = bool(re.search(r"<button[^>]*>\s*Topics\s*</button>", block, re.I))
    has_resources = bool(re.search(r"<button[^>]*>\s*Resources\s*</button>", block, re.I))
    # The validator requires a double-quoted Home link (single-quoted form is rejected).
    has_canonical_home = bool(re.search(r'<a\s+href="/"[^>]*>\s*Home\s*</a>', block, re.I))
    return not (has_topics and has_resources and has_canonical_home)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    canonical = extract_canonical_nav()
    targets = discover_targets()

    rewritten = []
    inserted = []
    skipped = []
    failed = []

    for path, kind in targets:
        html = path.read_text(encoding="utf-8")
        new_nav = adjust_active(canonical, kind)

        if not needs_backfill(html):
            skipped.append(path)
            continue

        if NAV_RE.search(html):
            new_html, n = NAV_RE.subn(new_nav, html, count=1)
            if n != 1:
                failed.append(path)
                continue
            rewritten.append(path)
        else:
            # No nav at all — inject before </header>
            insertion = "    " + new_nav + "\n  "
            new_html, n = HEADER_END_RE.subn(
                insertion + "</header>", html, count=1
            )
            if n != 1:
                failed.append(path)
                continue
            inserted.append(path)

        if not args.dry_run:
            path.write_text(new_html, encoding="utf-8")

    print(f"Rewritten (replaced existing nav): {len(rewritten)}")
    print(f"Inserted  (no nav was present):    {len(inserted)}")
    print(f"Skipped   (already canonical):     {len(skipped)}")
    print(f"Failed:                            {len(failed)}")

    if failed:
        print("\nFailed files:")
        for p in failed:
            print(f"  {p.relative_to(REPO_ROOT)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
