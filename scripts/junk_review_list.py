"""Parse the junk-voice review markdown written by scripts/report_junk_voices.py.

Shared by scripts/prepare_noindex.py and scripts/delete_junk_voices.py so both
read Tom's approvals the same way.

The review file has sections "## A. ...", "## B. ...", "## C. ..." whose items
look like

    - [ ] `slug` — Display Name
    - [x] `slug` — Display Name      <- ticked = approved

Section C lists duplicate *pairs* (`a` / `b`). Those need a human merge (which
page survives, which bio content moves), so neither script will act on them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from curator.voice_filters import HUB_SLUGS  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
VOICES_DIR = DOCS_DIR / "voices"
VOICES_DATA_PATH = DOCS_DIR / "voices_data.json"
SITEMAP_VOICES_PATH = DOCS_DIR / "sitemap-voices.xml"
NOINDEX_LIST_PATH = REPO_ROOT / "frontend" / "voices_noindex.json"
DEFAULT_REVIEW = REPO_ROOT / ".christian-orchestrator" / "junk-voices-review-2026-10-25.md"
SITE = "https://www.christiancurator.com"

_SECTION_RE = re.compile(r"^##\s+([A-Z])\.")
_ITEM_RE = re.compile(r"^- \[( |x|X)\] `([a-z0-9-]+)`(?! /)")
ACTIONABLE_SECTIONS = {"A", "B"}


def parse_review(path: Path) -> list[dict]:
    """Return [{"slug", "section", "checked"}] for every single-slug item."""
    items, section = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1)
            continue
        m = _ITEM_RE.match(line)
        if m and section:
            items.append({"slug": m.group(2), "section": section,
                          "checked": m.group(1).lower() == "x"})
    return items


def select(items: list[dict], sections: set[str], include_unchecked: bool) -> list[dict]:
    bad = sections - ACTIONABLE_SECTIONS
    if bad:
        sys.exit(f"Section(s) {sorted(bad)} are not actionable by script "
                 "(C = duplicate pairs need a manual merge).")
    chosen = [i for i in items if i["section"] in sections
              and (i["checked"] or include_unchecked)]
    # Never touch a hub page, whatever the review file says.
    return [i for i in chosen if i["slug"] not in HUB_SLUGS]


def remove_from_sitemap(slugs: set[str], apply: bool) -> int:
    """Drop <url> blocks for the given voice slugs from sitemap-voices.xml."""
    xml = SITEMAP_VOICES_PATH.read_text(encoding="utf-8")
    removed = 0

    def drop(m: re.Match) -> str:
        nonlocal removed
        if m.group(2) in slugs:
            removed += 1
            return ""
        return m.group(0)

    new = re.sub(r"(  <url>\s*<loc>" + re.escape(SITE) + r"/voices/([a-z0-9-]+)/</loc>.*?</url>\n)",
                 drop, xml, flags=re.S)
    if apply and removed:
        SITEMAP_VOICES_PATH.write_text(new, encoding="utf-8")
    return removed


def add_common_args(ap) -> None:
    ap.add_argument("--review", type=Path, default=DEFAULT_REVIEW,
                    help=f"review markdown (default: {DEFAULT_REVIEW.relative_to(REPO_ROOT)})")
    ap.add_argument("--sections", default="A",
                    help="comma-separated sections to act on: A and/or B (default: A)")
    ap.add_argument("--include-unchecked", action="store_true",
                    help="treat every listed item in the chosen sections as approved, "
                         "not only the ticked [x] ones")
    ap.add_argument("--only", default="",
                    help="comma-separated slugs to restrict to (for a small trial run)")
    ap.add_argument("--apply", action="store_true",
                    help="actually change files (default is a dry run that changes nothing)")
