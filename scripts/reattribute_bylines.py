#!/usr/bin/env python3
"""Reattribute archived bylines from the article pages (voices cleanup, Nov 12 2026).

The First Things fix (retire_posting_accounts.py) at four more outlets, where
the feed creator is not the writer:
  - Christianity Today: the feed and Yoast's JSON-LD author name the editing
    account (point_editor); the visible byline is ga4ArticleContext.byline.
  - 9Marks: the posting account (Jeri Choi) on every item.
  - WORLD: posting accounts (Keegan Martin on podcasts, Arla Eicher on
    roundups). Podcast episodes are media and carry no byline at all.
  - Pew Research: producer and newsletter accounts.
Plus single pieces the voices audit found miscredited elsewhere (EXTRA_URLS).

For every archived article on those domains the byline is read from the page
(fetcher.rss_fetcher.page_byline). When it differs from the archive byline,
the byline is rewritten on the archive day page (and the live homepage and
digest), in meta.json and in yesterday.json. A page that cannot be read keeps
its byline unless the byline is a known posting account (POSTING_ACCOUNTS),
which is then removed: a posting account is never credited.

DRY RUN BY DEFAULT. --apply writes. Pages are read from the backfill page
cache (/tmp/cc_pages, see backfill_original_titles.py) before fetching.
Afterwards: retire_posting_accounts.py --apply, build_voice_hubs.py,
build_recent_articles.py.
"""
from __future__ import annotations

import argparse
import gzip
import html as html_mod
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import requests  # noqa: E402

from backfill_original_titles import HEADERS, page_cache_path  # noqa: E402
from fetcher.rss_fetcher import page_byline  # noqa: E402
from frontend import load_voices_by_name  # noqa: E402

DOCS = REPO_ROOT / "docs"
ARCHIVE = DOCS / "archive"
YESTERDAY = DOCS / "yesterday.json"
REPORT = REPO_ROOT / ".christian-orchestrator" / "reattribution-2026-11-12.json"

DOMAINS = ("christianitytoday.com", "9marks.org", "wng.org", "pewresearch.org")
PODCAST_RE = re.compile(r"wng\.org/podcasts/")
# Pieces the audit found credited to someone the page does not name.
EXTRA_URLS = {
    "https://www.thegospelcoalition.org/article/teens-whole-bible/",
    "https://www.thegospelcoalition.org/article/10-resolutions-ai/",
}
POSTING_ACCOUNTS = {
    "Jeri Choi", "Keegan Martin", "Arla Eicher",
    "Anna Jackson", "Beshay Sakla", "Reem Nadeem", "Sara Atske",
}

ARTICLE_RE = re.compile(r"<article\b.*?</article>", re.S)
TITLE_URL_RE = re.compile(r'<a href="(https?://[^"]+)" class="cc-[a-z-]*title[a-z-]*"')
META_DIV_RE = re.compile(r'(<div class="cc-(article|lead|headline)-meta">)(.*?)(</div>)', re.S)
DOT = '<span class="cc-meta-dot">·</span>'


def split_names(author: str) -> list[str]:
    parts = re.split(r",|;|\s+and\s+|\s+&\s+", author or "", flags=re.IGNORECASE)
    return [p.strip(" \t\n\r.") for p in parts if p.strip(" \t\n\r.")]


def same_byline(a: str, b: str) -> bool:
    norm = lambda s: sorted(re.sub(r"[^a-z]", "", n.lower()) for n in split_names(s))  # noqa: E731
    return norm(a) == norm(b)


def in_scope(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return url in EXTRA_URLS or any(host == d or host.endswith("." + d) for d in DOMAINS)


def read_page(url: str, cache_dir: Path, fetch: bool) -> str | None:
    path = page_cache_path(cache_dir, url)
    if path.exists():
        return gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
    if not fetch:
        return None
    for attempt in range(2):
        try:
            time.sleep(1.0 + attempt * 4)
            resp = requests.get(url, timeout=20, headers=HEADERS)
        except Exception:  # noqa: BLE001
            continue
        if resp.status_code == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(resp.text.encode("utf-8", "replace")))
            return resp.text
        if resp.status_code not in (202, 429, 503):
            return None
    return None


def real_byline(url: str, current: str, cache_dir: Path, fetch: bool) -> tuple[str | None, str]:
    """(new byline or None to keep, reason)."""
    if PODCAST_RE.search(url):
        return "", "podcast episode: media, no byline"
    page = read_page(url, cache_dir, fetch)
    if page is None:
        if any(n in POSTING_ACCOUNTS for n in split_names(current)):
            return "", "page unreadable; posting account removed"
        return None, "page unreadable; kept"
    found = page_byline(page)
    return found, "page byline" if found else "page names no writer"


def byline_html(author: str, by_name: dict, kind: str) -> str:
    css = {"lead": "cc-author-link cc-lead-author"}.get(kind, "cc-author-link cc-article-author")
    out = []
    for name in split_names(author):
        slug = by_name.get(name.lower(), "")
        esc = html_mod.escape(name)
        out.append(f'<a href="/voices/{slug}/" class="{css}"><strong>{esc}</strong></a>' if slug
                   else f'<span class="{css}"><strong>{esc}</strong></span>')
    return ", ".join(out)


def rewrite_meta_div(inner: str, author: str, source: str, by_name: dict, kind: str) -> str:
    """Rebuild the byline part of a meta div, keeping the source and date."""
    src_span = f"<span>{html_mod.escape(source)}</span>"
    pos = inner.find(src_span) if source else -1
    if pos == -1:
        # Older markup: source shown as the only author slot (no byline).
        m = re.search(r'<span class="cc-lead-author">([^<]*)</span>', inner)
        if m and m.group(1).strip() == source:
            pos = m.start()
            src_span = f"<span>{html_mod.escape(source)}</span>"
            rest = inner[m.end():]
        else:
            return inner
    else:
        rest = inner[pos + len(src_span):]
    lead_ws = re.match(r"\s*", inner).group(0)
    new = byline_html(author, by_name, kind)
    if new:
        return f"{lead_ws}{new}\n          {DOT}\n          {src_span}{rest}"
    return f"{lead_ws}{src_span}{rest}"


# Homepage (front page, rebuilt each morning): title link then <div class="cc-src">.
HOME_SRC_RE = re.compile(
    r'(<a href="(https?://[^"]+)" class="cc-[a-z]+-title"[^>]*>.*?</a>\s*<div class="cc-src">)(.*?)(</div>)',
    re.S)


def fix_home(m: re.Match, changes: dict, sources: dict, by_name: dict) -> str:
    ch = changes.get(m.group(2))
    if not ch:
        return m.group(0)
    src = html_mod.escape(sources.get(m.group(2), ""))
    names = []
    for name in split_names(ch["to"]):
        slug = by_name.get(name.lower(), "")
        esc = html_mod.escape(name)
        names.append(f'<a href="/voices/{slug}/" class="cc-author-link"><strong>{esc}</strong></a>'
                     if slug else f"<strong>{esc}</strong>")
    inner = f"{', '.join(names)} &middot; {src}" if names else f"<strong>{src}</strong>"
    return m.group(1) + inner + m.group(4)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="use only cached pages")
    ap.add_argument("--page-cache", default="/tmp/cc_pages")
    args = ap.parse_args(argv)
    cache_dir = Path(args.page_cache)
    by_name = load_voices_by_name()
    for name in POSTING_ACCOUNTS:
        by_name.pop(name.lower(), None)

    # 1. Decide each in-scope URL's byline from meta.json rows.
    current: dict[str, str] = {}
    sources: dict[str, str] = {}
    for meta in sorted(ARCHIVE.glob("*/meta.json")):
        for a in json.loads(meta.read_text(encoding="utf-8")).get("articles", []):
            if a.get("url") and in_scope(a["url"]):
                current.setdefault(a["url"], a.get("author", ""))
                sources.setdefault(a["url"], a.get("source", ""))
    changes: dict[str, dict] = {}
    for i, url in enumerate(sorted(current)):
        new, why = real_byline(url, current[url], cache_dir, fetch=not args.no_fetch)
        if new is not None and not same_byline(new, current[url]):
            changes[url] = {"from": current[url], "to": new, "why": why}
    print(f"{len(current)} archived pieces on {', '.join(DOMAINS)} (+{len(EXTRA_URLS)} extra); "
          f"{len(changes)} bylines change")

    # 2. Archive day pages, homepage and digest.
    pages = blocks = 0
    targets = [d / "index.html" for d in sorted(ARCHIVE.iterdir()) if (d / "index.html").exists()]
    targets += [DOCS / "index.html", DOCS / "digest" / "index.html"]
    for path in targets:
        page = path.read_text(encoding="utf-8", errors="replace")

        def fix_block(m: re.Match) -> str:
            nonlocal blocks
            block = m.group(0)
            t = TITLE_URL_RE.search(block)
            if not t or t.group(1) not in changes:
                return block
            ch = changes[t.group(1)]
            src = sources.get(t.group(1), "")
            out = META_DIV_RE.sub(lambda d: d.group(1) + rewrite_meta_div(
                d.group(3), ch["to"], src, by_name, d.group(2)) + d.group(4), block, count=1)
            if out != block:
                blocks += 1
            return out

        new = ARTICLE_RE.sub(fix_block, page)
        if path == DOCS / "index.html":
            new = HOME_SRC_RE.sub(lambda m: fix_home(m, changes, sources, by_name), new)
        if new != page:
            pages += 1
            if args.apply:
                path.write_text(new, encoding="utf-8")
    print(f"{blocks} byline blocks on {pages} pages {'rewritten' if args.apply else 'would change'}")

    # 3. meta.json and yesterday.json.
    metas = 0
    for meta in sorted(ARCHIVE.glob("*/meta.json")):
        d = json.loads(meta.read_text(encoding="utf-8"))
        dirty = False
        for a in d.get("articles", []):
            ch = changes.get(a.get("url", ""))
            if ch:
                a["author"], a["authors"] = ch["to"], split_names(ch["to"])
                dirty = True
        if dirty:
            d["authors"] = sorted({n for a in d.get("articles", []) for n in a.get("authors", [])})
            metas += 1
            if args.apply:
                meta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    rows = json.loads(YESTERDAY.read_text(encoding="utf-8"))
    y = 0
    for r in rows:
        ch = changes.get(r.get("url", ""))
        if ch:
            r["author"] = ch["to"]
            y += 1
    if args.apply:
        YESTERDAY.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        REPORT.write_text(json.dumps(changes, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{metas} meta.json files, {y} yesterday.json rows")

    by_from: dict[str, int] = {}
    for ch in changes.values():
        for n in split_names(ch["from"]) or ["(none)"]:
            by_from[n] = by_from.get(n, 0) + 1
    for n, k in sorted(by_from.items(), key=lambda t: -t[1])[:40]:
        print(f"  {k:4d}  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
