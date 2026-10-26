#!/usr/bin/env python3
"""Merge duplicate voice pages (review section C) into one surviving page.

For each loser -> survivor pair in PAIRS:
  1. retargets every <a href="/voices/<loser>/"> under docs/ to the survivor, so
     the loser's articles show up in the survivor's "Recent Articles" block
  2. removes the loser from docs/voices_data.json and its /voices/ index card
  3. replaces docs/voices/<loser>/index.html with a noindex redirect stub
     (meta refresh + rel=canonical to the survivor)
  4. records the pair in frontend/voices_redirects.json (bylines under the
     loser's name then link to the survivor, and backfill_voices_data.py won't
     re-add the stub), adds the loser to frontend/voices_noindex.json and
     drops it from docs/sitemap-voices.xml
  5. refreshes the "Recent Articles" block on each survivor page

The survivor keeps its own bio and metadata: the losers' bios are mostly
boilerplate or unverified, so nothing is copied across.

DRY RUN BY DEFAULT. Nothing is written unless --apply is passed. Idempotent.

    python3 scripts/merge_duplicate_voices.py            # dry run
    python3 scripts/merge_duplicate_voices.py --apply
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys

from junk_review_list import (
    DOCS_DIR, NOINDEX_LIST_PATH, REPO_ROOT, SITE, VOICES_DATA_PATH, VOICES_DIR,
    remove_from_sitemap,
)
from curator.voice_filters import HUB_SLUGS  # noqa: E402  (path set by junk_review_list)
from delete_junk_voices import INDEX_PATH, card_re
import build_recent_articles as recent

REDIRECTS_PATH = REPO_ROOT / "frontend" / "voices_redirects.json"

# loser -> survivor. Chosen on 2026-10-26 from review section C: the survivor is
# the page with the richer, more accurate bio and more inbound links; on a tie,
# the slug matching the author's published byline. michael-brown /
# michael-g-brown is deliberately absent: they are two different people.
PAIRS = {
    "o-alan-noble": "alan-noble",
    "andrew-j-spencer": "andrew-spencer",
    "brandon-crowe": "brandon-d-crowe",
    "brian-najapfour": "brian-g-najapfour",
    "carl-r-trueman": "carl-trueman",
    "daniel-hyde": "daniel-r-hyde",
    "dr-owen-anderson": "owen-anderson",
    "jeffrey-stivason": "jeffrey-a-stivason",
    "keith-a-mathison": "keith-mathison",
    "kevin-j-vanhoozer": "kevin-vanhoozer",
    "pastor-rich-bitterman": "rich-bitterman",
    "samuel-james": "samuel-d-james",
}

STUB = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{name} — Christian Curator</title>
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{site}/voices/{to}/" />
  <meta http-equiv="refresh" content="0; url=/voices/{to}/" />
</head>
<body data-pagefind-ignore="all">
  <p>This page has moved to <a href="/voices/{to}/">{name}</a>.</p>
</body>
</html>
"""


def href_re(slug: str) -> re.Pattern:
    return re.compile(r'href="(?:' + re.escape(SITE) + r')?/voices/' + re.escape(slug) + r'/"')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually change files (default is a dry run)")
    args = ap.parse_args()
    print(f"merge_duplicate_voices — {'APPLY' if args.apply else 'DRY RUN (no files changed)'}")

    data = json.loads(VOICES_DATA_PATH.read_text(encoding="utf-8"))
    by_slug = {v["slug"]: v for v in data}
    redirects = json.loads(REDIRECTS_PATH.read_text()) if REDIRECTS_PATH.exists() else {}

    for loser, to in PAIRS.items():
        if to not in by_slug or not (VOICES_DIR / to / "index.html").exists():
            sys.exit(f"survivor {to} is missing from voices_data.json or disk; aborting")
        name = by_slug[to]["name"]
        loser_name = by_slug.get(loser, {}).get("name") or redirects.get(loser, {}).get("name", "")
        redirects[loser] = {"to": to, "name": loser_name}
        print(f"  {loser} -> {to}  ({loser_name or '?'} -> {name})")

    # 1. Retarget inbound links (skip the loser pages themselves, the index and
    #    hubs, which are rewritten below / rebuilt from voices_data.json).
    skip = {VOICES_DIR / s for s in PAIRS} | {VOICES_DIR / h for h in HUB_SLUGS}
    pages = links = 0
    for page in DOCS_DIR.rglob("*.html"):
        if page == INDEX_PATH or any(d in page.parents for d in skip):
            continue
        html = page.read_text(encoding="utf-8", errors="ignore")
        if "/voices/" not in html:
            continue
        new = html
        for loser, to in PAIRS.items():
            new, n = href_re(loser).subn(f'href="/voices/{to}/"', new)
            links += n
        if new != html:
            pages += 1
            if args.apply:
                page.write_text(new, encoding="utf-8")

    # 2. Data entries and index cards.
    kept = [v for v in data if v["slug"] not in PAIRS]
    index_html = INDEX_PATH.read_text(encoding="utf-8")
    cards = 0
    for loser in PAIRS:
        index_html, n = card_re(loser).subn("", index_html)
        cards += n
    index_html = re.sub(r"— \d+ voices worth following\.", f"— {len(kept)} voices worth following.", index_html)

    # 3-4. Stubs, redirect map, noindex list, sitemap.
    noindex = set(json.loads(NOINDEX_LIST_PATH.read_text())) if NOINDEX_LIST_PATH.exists() else set()
    sitemap_removed = remove_from_sitemap(set(PAIRS), args.apply)
    if args.apply:
        for loser, to in PAIRS.items():
            stub = STUB.format(name=html_mod.escape(by_slug[to]["name"]), site=SITE, to=to)
            (VOICES_DIR / loser).mkdir(exist_ok=True)
            (VOICES_DIR / loser / "index.html").write_text(stub, encoding="utf-8")
        VOICES_DATA_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        INDEX_PATH.write_text(index_html, encoding="utf-8")
        REDIRECTS_PATH.write_text(json.dumps(dict(sorted(redirects.items())), indent=2) + "\n", encoding="utf-8")
        NOINDEX_LIST_PATH.write_text(json.dumps(sorted(noindex | set(PAIRS)), indent=2) + "\n", encoding="utf-8")

    # 5. Refresh survivors' Recent Articles blocks from the retargeted archive links.
    refreshed = 0
    if args.apply:
        by_voice = recent.collect_by_voice()
        for to in sorted(set(PAIRS.values())):
            items = by_voice.get(to)
            page = VOICES_DIR / to / "index.html"
            if not items:
                continue
            html = page.read_text(encoding="utf-8")
            out = recent.inject(html, recent.render_section(
                "From Our Daily Digest", f"Recent Articles by {by_slug[to]['name']}", items))
            if out and out != html:
                page.write_text(out, encoding="utf-8")
                refreshed += 1

    verb = "" if args.apply else "would be "
    print(f"\n{len(PAIRS)} loser page(s) {verb}replaced with redirect stubs.")
    print(f"{links} link(s) on {pages} page(s) {verb}retargeted to survivors.")
    print(f"{len(data) - len(kept)} voices_data.json entr(ies) {verb}removed ({len(kept)} remain).")
    print(f"{cards} /voices/ card(s) {verb}removed; {sitemap_removed} sitemap URL(s) {verb}removed.")
    if args.apply:
        print(f"{refreshed} survivor page(s) had their Recent Articles block refreshed.")
        print("\nNext: python3 scripts/build_voice_hubs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
