#!/usr/bin/env python3
"""Delete approved junk voice pages and every reference the site keeps to them.

Reads the junk-voice review list and, for each approved slug:
  1. deletes docs/voices/<slug>/
  2. removes its entry from docs/voices_data.json
  3. removes its <url> from docs/sitemap-voices.xml
  4. removes its card from docs/voices/index.html
  5. drops it from frontend/voices_noindex.json if it was noindexed earlier
  6. with --unlink: turns any other <a href="/voices/<slug>/">text</a> under docs/
     into plain text so nothing on the site links to a 404

The 8 /voices/<hub>/ pages are not edited here: they rebuild from
voices_data.json, so run scripts/build_voice_hubs.py afterwards (see the runbook).

DRY RUN BY DEFAULT. Nothing is written or deleted unless --apply is passed.

    python3 scripts/delete_junk_voices.py                      # dry run, ticked items in section A
    python3 scripts/delete_junk_voices.py --sections A --include-unchecked --unlink
    python3 scripts/delete_junk_voices.py --apply --unlink     # act on ticked section-A items

Section C (duplicate pairs) is never handled here; merge those by hand.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys

from junk_review_list import (
    DOCS_DIR, NOINDEX_LIST_PATH, REPO_ROOT, SITE, VOICES_DATA_PATH, VOICES_DIR,
    add_common_args, parse_review, remove_from_sitemap, select,
)
from curator.voice_filters import HUB_SLUGS  # noqa: E402  (path set by junk_review_list)

INDEX_PATH = VOICES_DIR / "index.html"


def card_re(slug: str) -> re.Pattern:
    return re.compile(r'[ \t]*<a href="/voices/' + re.escape(slug)
                      + r'/" class="cc-voice-card">.*?</a>\n?', re.S)


def link_re(slug: str) -> re.Pattern:
    return re.compile(r'<a\b[^>]*href="(?:' + re.escape(SITE) + r')?/voices/' + re.escape(slug)
                      + r'/"[^>]*>(.*?)</a>', re.S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--unlink", action="store_true",
                    help="also strip <a> links to deleted pages elsewhere under docs/ (keeps the link text)")
    args = ap.parse_args()

    sections = {s.strip().upper() for s in args.sections.split(",") if s.strip()}
    items = select(parse_review(args.review), sections, args.include_unchecked)
    if args.only:
        only = {s.strip() for s in args.only.split(",")}
        items = [i for i in items if i["slug"] in only]

    mode = "APPLY" if args.apply else "DRY RUN (nothing deleted or changed)"
    print(f"delete_junk_voices — {mode}")
    print(f"review: {args.review.relative_to(REPO_ROOT)}  sections: {','.join(sorted(sections))}  "
          f"{'all listed' if args.include_unchecked else 'ticked [x] only'}")
    if not items:
        print("Nothing selected. Tick items ([x]) in the review file or pass --include-unchecked.")
        return 0

    slugs = {i["slug"] for i in items if i["slug"] not in HUB_SLUGS}
    on_disk = {s for s in slugs if (VOICES_DIR / s).is_dir()}

    data = json.loads(VOICES_DATA_PATH.read_text(encoding="utf-8"))
    kept = [v for v in data if v.get("slug") not in slugs]
    data_removed = len(data) - len(kept)

    index_html = INDEX_PATH.read_text(encoding="utf-8")
    cards_removed = 0
    for s in slugs:
        index_html, n = card_re(s).subn("", index_html)
        cards_removed += n

    # Other pages that link to a doomed slug (excluding the pages being deleted,
    # the voices index handled above, and hub pages that rebuild from data).
    skip_dirs = {VOICES_DIR / s for s in slugs} | {VOICES_DIR / h for h in HUB_SLUGS}
    inbound: dict = {}
    for page in DOCS_DIR.rglob("*.html"):
        if page == INDEX_PATH or any(d in page.parents for d in skip_dirs):
            continue
        html = page.read_text(encoding="utf-8", errors="ignore")
        if "/voices/" not in html:
            continue
        hits = [s for s in slugs if f"/voices/{s}/" in html]
        if hits:
            inbound[page] = hits

    for it in sorted(items, key=lambda i: (i["section"], i["slug"])):
        flag = "-" if it["slug"] in on_disk else "?"
        print(f"  {flag}  [{it['section']}] {it['slug']}{'' if flag == '-' else '  (no page on disk)'}")

    sitemap_removed = remove_from_sitemap(slugs, args.apply)
    noindex = set(json.loads(NOINDEX_LIST_PATH.read_text())) if NOINDEX_LIST_PATH.exists() else set()
    noindex_removed = len(noindex & slugs)

    unlinked = 0
    if args.unlink:
        for page, hits in inbound.items():
            html = page.read_text(encoding="utf-8")
            new = html
            for s in hits:
                new, n = link_re(s).subn(r"\1", new)
                unlinked += n
            if args.apply and new != html:
                page.write_text(new, encoding="utf-8")

    if args.apply:
        for s in sorted(on_disk):
            shutil.rmtree(VOICES_DIR / s)
        VOICES_DATA_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        INDEX_PATH.write_text(index_html, encoding="utf-8")
        if noindex_removed:
            NOINDEX_LIST_PATH.write_text(json.dumps(sorted(noindex - slugs), indent=2) + "\n", encoding="utf-8")

    verb = "" if args.apply else "would be "
    print(f"\n{len(on_disk)} page director(ies) {verb}deleted ({len(slugs) - len(on_disk)} already gone).")
    print(f"{data_removed} entr(ies) {verb}removed from docs/voices_data.json ({len(kept)} remain).")
    print(f"{sitemap_removed} URL(s) {verb}removed from docs/sitemap-voices.xml.")
    print(f"{cards_removed} card(s) {verb}removed from docs/voices/index.html.")
    if noindex_removed:
        print(f"{noindex_removed} slug(s) {verb}removed from frontend/voices_noindex.json.")
    print(f"{len(inbound)} other page(s) link to these slugs"
          + (f"; {unlinked} link(s) {verb}converted to plain text." if args.unlink
             else " (pass --unlink to strip those links)."))
    for page, hits in sorted(inbound.items())[:15]:
        print(f"    {page.relative_to(REPO_ROOT)}: {', '.join(sorted(hits))}")
    if len(inbound) > 15:
        print(f"    … and {len(inbound) - 15} more")
    if args.apply:
        print("\nNext: python3 scripts/build_voice_hubs.py  (rebuild the 8 hub pages from voices_data.json)")
    else:
        print("\nRe-run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
