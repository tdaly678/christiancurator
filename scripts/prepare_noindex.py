#!/usr/bin/env python3
"""Mark approved junk voice pages noindex (reversible alternative to deletion).

Reads the junk-voice review list and, for each approved slug:
  1. adds/normalises <meta name="robots" content="noindex, follow" /> in <head>
  2. records the slug in frontend/voices_noindex.json, which regenerate_sitemap()
     reads so the daily run keeps it out of sitemap-voices.xml
  3. removes its <url> from docs/sitemap-voices.xml now (a noindexed URL in a
     sitemap is a conflicting signal)

The page itself, its voices_data.json entry and all links to it stay in place.

DRY RUN BY DEFAULT. Nothing is written unless --apply is passed.

    python3 scripts/prepare_noindex.py                       # dry run, ticked items in section A
    python3 scripts/prepare_noindex.py --sections A,B --include-unchecked
    python3 scripts/prepare_noindex.py --apply               # act on ticked section-A items

Idempotent: re-running with --apply changes nothing further.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from junk_review_list import (
    NOINDEX_LIST_PATH, REPO_ROOT, VOICES_DIR, add_common_args, parse_review,
    remove_from_sitemap, select,
)

ROBOTS_TAG = '<meta name="robots" content="noindex, follow" />'
_ROBOTS_RE = re.compile(r'<meta\s+name="robots"[^>]*>', re.IGNORECASE)


def noindex_html(html: str) -> tuple[str, str]:
    """Return (new_html, action) where action is 'added', 'replaced' or 'already'."""
    m = _ROBOTS_RE.search(html)
    if m:
        if "noindex" in m.group(0).lower():
            return html, "already"
        return html[:m.start()] + ROBOTS_TAG + html[m.end():], "replaced"
    new, n = re.subn(r"(<title>[^<]*</title>)", r"\1\n  " + ROBOTS_TAG, html, count=1)
    if not n:
        new, n = re.subn(r"(<head[^>]*>)", r"\1\n  " + ROBOTS_TAG, html, count=1)
    if not n:
        raise ValueError("no <head> found")
    return new, "added"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    args = ap.parse_args()

    sections = {s.strip().upper() for s in args.sections.split(",") if s.strip()}
    items = select(parse_review(args.review), sections, args.include_unchecked)
    if args.only:
        only = {s.strip() for s in args.only.split(",")}
        items = [i for i in items if i["slug"] in only]

    mode = "APPLY" if args.apply else "DRY RUN (no files changed)"
    print(f"prepare_noindex — {mode}")
    print(f"review: {args.review.relative_to(REPO_ROOT)}  sections: {','.join(sorted(sections))}  "
          f"{'all listed' if args.include_unchecked else 'ticked [x] only'}")
    if not items:
        print("Nothing selected. Tick items ([x]) in the review file or pass --include-unchecked.")
        return 0

    noindex = set(json.loads(NOINDEX_LIST_PATH.read_text())) if NOINDEX_LIST_PATH.exists() else set()
    counts = {"added": 0, "replaced": 0, "already": 0, "missing": 0}
    targeted = set()
    for it in items:
        slug = it["slug"]
        page = VOICES_DIR / slug / "index.html"
        if not page.exists():
            counts["missing"] += 1
            print(f"  ?  {slug}  (no page on disk; skipped)")
            continue
        html = page.read_text(encoding="utf-8")
        new, action = noindex_html(html)
        counts[action] += 1
        targeted.add(slug)
        print(f"  {'·' if action == 'already' else '+'}  [{it['section']}] {slug}  ({action})")
        if args.apply and new != html:
            page.write_text(new, encoding="utf-8")

    sitemap_removed = remove_from_sitemap(targeted, args.apply)
    new_list = sorted(noindex | targeted)
    if args.apply:
        NOINDEX_LIST_PATH.write_text(json.dumps(new_list, indent=2) + "\n", encoding="utf-8")

    verb = "" if args.apply else "would be "
    print(f"\n{len(targeted)} page(s) {verb}noindexed: {counts['added']} added, "
          f"{counts['replaced']} replaced, {counts['already']} already noindex; {counts['missing']} missing.")
    print(f"{sitemap_removed} URL(s) {verb}removed from docs/sitemap-voices.xml.")
    print(f"frontend/voices_noindex.json {verb}listing {len(new_list)} slug(s).")
    if not args.apply:
        print("\nRe-run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
