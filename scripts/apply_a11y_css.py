#!/usr/bin/env python3
"""Apply the contrast and tap-target CSS to published static pages.

Pages rendered from the templates or generators pick the fix up on their next
render; this script brings the pages that are not re-rendered every day
(voice pages, archive and daily pages, About, 404) in line now. It edits only
CSS: the <head> styles, style="" attributes, and the CC-A11Y block (see
frontend/a11y_css.py). Topic pages are not touched; docs/assets/topic.css
carries their overrides. Idempotent. Dry run by default; --apply writes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from frontend.a11y_css import fix_page  # noqa: E402

DOCS = ROOT / "docs"


def pages() -> list[Path]:
    out = [DOCS / "index.html", DOCS / "404.html", DOCS / "about" / "index.html",
           DOCS / "digest" / "index.html", DOCS / "archive" / "index.html"]
    out += sorted((DOCS / "archive").glob("*/index.html"))
    out += sorted((DOCS / "daily").glob("*/index.html"))
    out += sorted((DOCS / "voices").rglob("index.html"))
    return [p for p in out if p.exists()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    changed = 0
    for path in pages():
        html = path.read_text(encoding="utf-8")
        new = fix_page(html)
        if new != html:
            changed += 1
            if args.apply:
                path.write_text(new, encoding="utf-8")
    print(f"{'Rewrote' if args.apply else 'Would rewrite'} {changed} page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
