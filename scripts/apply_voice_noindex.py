#!/usr/bin/env python3
"""Noindex a list of voice pages and take them out of sitemap-voices.xml.

Voices cleanup step 5 (Nov 12 2026): the voices audit marked 994 pages
noindex (no or one digest piece and an unsourced bio, or a secular reporter).
Their slugs are in data/voices/noindex-2026-11-12.txt. For each slug this
script:
  1. adds or normalises <meta name="robots" content="noindex, follow" />;
  2. records the slug in frontend/voices_noindex.json (regenerate_sitemap()
     keeps listed slugs out of sitemap-voices.xml on every daily run);
  3. removes its <url> from docs/sitemap-voices.xml now.
Pages, voices_data.json entries and every link to them stay in place, so a
page can be reindexed later by removing it from the list.

DRY RUN BY DEFAULT. --apply writes. Idempotent.

    python3 scripts/apply_voice_noindex.py data/voices/noindex-2026-11-12.txt --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from junk_review_list import NOINDEX_LIST_PATH, VOICES_DIR, remove_from_sitemap  # noqa: E402
from curator.voice_generator import noindex_page  # noqa: E402  (path set by junk_review_list)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("slug_file", type=Path)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    slugs = [s.strip() for s in args.slug_file.read_text().split() if s.strip()]
    listed = set(json.loads(NOINDEX_LIST_PATH.read_text())) if NOINDEX_LIST_PATH.exists() else set()

    tagged = missing = 0
    for slug in slugs:
        page = VOICES_DIR / slug / "index.html"
        if not page.exists():
            missing += 1
            continue
        html = page.read_text(encoding="utf-8")
        new = noindex_page(html)
        if new != html:
            tagged += 1
            if args.apply:
                page.write_text(new, encoding="utf-8")
    removed = remove_from_sitemap(set(slugs), args.apply)
    added = len(set(slugs) - listed)
    if args.apply:
        NOINDEX_LIST_PATH.write_text(json.dumps(sorted(listed | set(slugs)), indent=2) + "\n", encoding="utf-8")
    verb = "" if args.apply else "would be "
    print(f"{len(slugs)} slugs: robots tag {verb}added or normalised on {tagged} pages ({missing} missing); "
          f"{added} {verb}added to voices_noindex.json; {removed} sitemap URLs {verb}removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
