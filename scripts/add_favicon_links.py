#!/usr/bin/env python3
"""Add the favicon <link> block to every published page's <head>.

Templates and generators carry the block already (frontend/favicon.py); this
brings static pages (topic pages, voices, archive, daily, About, 404, hubs,
redirect stubs) in line. Head only, between CC-FAVICON markers, idempotent.
docs/email_draft.html (the email body) and Pagefind output are skipped.
Dry run by default; --apply writes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from frontend.favicon import add_favicon  # noqa: E402

DOCS = ROOT / "docs"
SKIP = {DOCS / "email_draft.html"}


def pages() -> list[Path]:
    return sorted(p for p in DOCS.rglob("*.html")
                  if p not in SKIP and "_pagefind" not in p.parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    changed = 0
    for path in pages():
        html = path.read_text(encoding="utf-8")
        new = add_favicon(html)
        if new != html:
            changed += 1
            if args.apply:
                path.write_text(new, encoding="utf-8")
    print(f"{'Rewrote' if args.apply else 'Would rewrite'} {changed} page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
