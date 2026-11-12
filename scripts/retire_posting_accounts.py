#!/usr/bin/env python3
"""Retire voice pages that belong to a publisher's posting account, not a writer.

First Things' feed puts the WordPress posting account in dc:creator, so our
archive credited First Things pieces to staff who did not write them (the
fetcher now reads the byline from each article page: `byline_from_page` in
fetcher/sources.py). For each slug in ACCOUNTS this script:
  1. finds every archived article credited to the account (day pages and
     their meta.json) and reads the real byline from the article page;
  2. rewrites the byline on each archive day page: a link to the real
     writer's voice page when one exists, plain text when not, and no byline
     at all when the page names nobody;
  3. fixes author/authors in each day's meta.json and re-renders
     docs/archive/index.html from them;
  4. replaces docs/voices/<slug>/index.html with a noindex redirect stub to
     /voices/ (meta refresh + rel=canonical), records the slug in
     frontend/voices_redirects.json with "to": "" (retired: bylines under
     that name are never linked), keeps it in voices_noindex.json and out of
     sitemap-voices.xml, and removes it from voices_data.json and the /voices/
     index.

DRY RUN BY DEFAULT. Pass --apply to write. Idempotent. Afterwards run
scripts/build_voice_hubs.py and scripts/build_recent_articles.py.

    python3 scripts/retire_posting_accounts.py
    python3 scripts/retire_posting_accounts.py --apply
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from junk_review_list import (
    DOCS_DIR, NOINDEX_LIST_PATH, REPO_ROOT, SITE, VOICES_DATA_PATH, VOICES_DIR,
    remove_from_sitemap,
)
from delete_junk_voices import INDEX_PATH, card_re

from fetcher.rss_fetcher import fetch_page_byline  # noqa: E402  (path set by junk_review_list)

ARCHIVE_DIR = DOCS_DIR / "archive"
REDIRECTS_PATH = REPO_ROOT / "frontend" / "voices_redirects.json"

# slug -> (name, outlet domain). Retired on Tom's call only.
ACCOUNTS = {
    "abby-silva": ("Abby Silva", "firstthings.com"),  # 2026-11-12, voices pilot go-live
    # 2026-11-12, voices batch 2 brief: the rest of the go-live audit.
    "german-saucedo": ("German Saucedo", "firstthings.com"),
    "paul-howard": ("Paul Howard", "firstthings.com"),
    "jillian-parks": ("Jillian Parks", "firstthings.com"),
    "stephen-walker": ("Stephen Walker", "firstthings.com"),
    "chloe-hoyle": ("Chloe Hoyle", "firstthings.com"),
}

STUB = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Voices | Christian Curator</title>
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{site}/voices/" />
  <meta http-equiv="refresh" content="0; url=/voices/" />
</head>
<body data-pagefind-ignore="all">
  <p>This page has moved to <a href="/voices/">Voices</a>.</p>
</body>
</html>
"""

URL_RE = re.compile(r'href="(https?://[^"]+)"')


def split_names(author: str) -> list[str]:
    parts = re.split(r",|;|\s+and\s+", author or "", flags=re.IGNORECASE)
    return [p.strip(" \t\n\r.") for p in parts if p.strip(" \t\n\r.")]


def byline_html(author: str, by_name: dict, css: str, strong: bool = True) -> str:
    out = []
    for name in split_names(author):
        slug = by_name.get(name.lower(), "")
        esc = html_mod.escape(name)
        text = f"<strong>{esc}</strong>" if strong else esc
        out.append(f'<a href="/voices/{slug}/" class="{css}">{text}</a>' if slug
                   else f'<span class="{css}">{text}</span>')
    return ", ".join(out)


def anchor_re(slug: str) -> re.Pattern:
    # The byline link, plus the "·" separator after it (dropped with an empty byline).
    # April 2026 archive pages have no <strong>; the homepage and digest use &middot;.
    return re.compile(
        r'<a href="(?:' + re.escape(SITE) + r')?/voices/' + re.escape(slug)
        + r'/" class="([^"]*)">(<strong>)?[^<]*(?:</strong>)?</a>'
        + r'(\s*(?:<span class="cc-meta-dot">·</span>|&middot;))?'
    )


def replace_byline(m: re.Match, author: str, by_name: dict) -> str:
    """Replacement for an anchor_re match: the real byline, or nothing (separator included)."""
    if not author:
        return ""
    return byline_html(author, by_name, m.group(1), strong=bool(m.group(2))) + (m.group(3) or "")


def byline_pages() -> list[Path]:
    """Archive day pages, plus the live homepage and digest (re-rendered daily,
    but they carry today's bylines until the next run)."""
    days = [d / "index.html" for d in sorted(ARCHIVE_DIR.iterdir()) if (d / "index.html").exists()]
    return days + [p for p in (DOCS_DIR / "index.html", DOCS_DIR / "digest" / "index.html") if p.exists()]


def credited_urls(slug: str, name: str, domain: str) -> set[str]:
    urls = set()
    for idx in byline_pages():
        page = idx.read_text(encoding="utf-8", errors="replace")
        for m in anchor_re(slug).finditer(page):
            prev = [u for u in URL_RE.findall(page[max(0, m.start() - 4000):m.start()]) if domain in u]
            if prev:
                urls.add(prev[-1])
    for day in sorted(ARCHIVE_DIR.iterdir()):
        meta = day / "meta.json"
        if meta.exists():
            for a in json.loads(meta.read_text(encoding="utf-8")).get("articles", []):
                if name in (a.get("authors") or []) or a.get("author") == name:
                    urls.add(a["url"])
    return urls


def retry_unreadable(urls: list[str], rounds: int = 3, pause: float = 1.5) -> dict[str, str | None]:
    """Refetch pages that failed in the parallel pass, one at a time.

    A large retirement (hundreds of pages) trips the publisher's rate limit, and
    an unreadable page would otherwise lose its byline entirely."""
    out: dict[str, str | None] = {}
    for attempt in range(rounds):
        todo = [u for u in urls if out.get(u) is None]
        if not todo:
            break
        if attempt:
            time.sleep(pause * 10)
        for u in todo:
            time.sleep(pause)
            out[u] = fetch_page_byline(u)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually change files (default is a dry run)")
    args = ap.parse_args()
    print(f"retire_posting_accounts: {'APPLY' if args.apply else 'DRY RUN (no files changed)'}")

    data = json.loads(VOICES_DATA_PATH.read_text(encoding="utf-8"))
    kept = [v for v in data if v["slug"] not in ACCOUNTS]
    by_name = {v["name"].lower(): v["slug"] for v in kept}
    noindex = set(json.loads(NOINDEX_LIST_PATH.read_text())) if NOINDEX_LIST_PATH.exists() else set()
    redirects = json.loads(REDIRECTS_PATH.read_text()) if REDIRECTS_PATH.exists() else {}
    for r in redirects.values():
        if r.get("name") and r.get("to"):
            by_name.setdefault(r["name"].lower(), r["to"])
    by_name = {n: s for n, s in by_name.items() if s not in noindex and s not in ACCOUNTS}

    real: dict[str, str] = {}
    for slug, (name, domain) in ACCOUNTS.items():
        urls = sorted(credited_urls(slug, name, domain))
        with ThreadPoolExecutor(max_workers=4) as pool:
            found = dict(zip(urls, pool.map(fetch_page_byline, urls)))
        found.update(retry_unreadable([u for u in urls if found[u] is None]))
        print(f"\n{slug} ({name}): {len(urls)} article(s)")
        for u in urls:
            real[u] = found[u] or ""
            shown = found[u] if found[u] else ("(page unreadable: no byline)" if found[u] is None else "(no byline on page)")
            linked = [n for n in split_names(real[u]) if n.lower() in by_name]
            print(f"  {u}\n      -> {shown}{'  [voice page: ' + ', '.join(linked) + ']' if linked else ''}")

    # 2. Archive day pages.
    day_pages = 0
    for idx in byline_pages():
        page = idx.read_text(encoding="utf-8", errors="replace")
        new = page
        for slug, (name, domain) in ACCOUNTS.items():
            def repl(m: re.Match) -> str:
                prev = [u for u in URL_RE.findall(new[max(0, m.start() - 4000):m.start()]) if domain in u]
                return replace_byline(m, real.get(prev[-1], "") if prev else "", by_name)
            new = anchor_re(slug).sub(repl, new)
        if new != page:
            day_pages += 1
            if args.apply:
                idx.write_text(new, encoding="utf-8")

    # 3. meta.json per day.
    metas = 0
    names = {name for name, _ in ACCOUNTS.values()}
    for meta in sorted(ARCHIVE_DIR.glob("*/meta.json")):
        d = json.loads(meta.read_text(encoding="utf-8"))
        changed = False
        for a in d.get("articles", []):
            if a.get("author") in names or names & set(a.get("authors") or []):
                author = real.get(a["url"], "")
                if (a.get("author"), a.get("authors")) != (author, split_names(author)):
                    a["author"], a["authors"] = author, split_names(author)
                    changed = True
        if changed:
            d["authors"] = sorted({n for a in d.get("articles", []) for n in a.get("authors", [])})
            metas += 1
            if args.apply:
                meta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    # 4. Stub, redirect map, noindex, sitemap, voices data and index card.
    index_html = INDEX_PATH.read_text(encoding="utf-8")
    cards = 0
    for slug in ACCOUNTS:
        index_html, n = card_re(slug).subn("", index_html)
        cards += n
    index_html = re.sub(r"(?:—|:) \d+ voices worth following\.", f": {len(kept)} voices worth following.", index_html)
    sitemap_removed = remove_from_sitemap(set(ACCOUNTS), args.apply)
    if args.apply:
        for slug, (name, _) in ACCOUNTS.items():
            (VOICES_DIR / slug).mkdir(exist_ok=True)
            (VOICES_DIR / slug / "index.html").write_text(STUB.format(site=SITE), encoding="utf-8")
            redirects[slug] = {"to": "", "name": name, "retired": "posting account, not a writer"}
        VOICES_DATA_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        INDEX_PATH.write_text(index_html, encoding="utf-8")
        REDIRECTS_PATH.write_text(json.dumps(dict(sorted(redirects.items())), indent=2) + "\n", encoding="utf-8")
        NOINDEX_LIST_PATH.write_text(json.dumps(sorted(noindex | set(ACCOUNTS)), indent=2) + "\n", encoding="utf-8")

        sys.path.insert(0, str(REPO_ROOT))
        from jinja2 import Environment, FileSystemLoader
        from frontend import TEMPLATE_DIR, render_archive_index
        render_archive_index(Environment(loader=FileSystemLoader(str(TEMPLATE_DIR))))

    verb = "" if args.apply else "would be "
    print(f"\n{day_pages} archive day page(s) and {metas} meta.json file(s) {verb}rewritten.")
    print(f"{len(data) - len(kept)} voices_data.json entr(ies) {verb}removed; {cards} /voices/ card(s) {verb}removed; "
          f"{sitemap_removed} sitemap URL(s) {verb}removed.")
    if args.apply:
        print("archive index re-rendered.\nNext: python3 scripts/build_voice_hubs.py && python3 scripts/build_recent_articles.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
