#!/usr/bin/env python3
"""Recover publisher headlines for articles saved before Nov 12 2026.

Archive pages, archive meta.json, yesterday.json and article_history.json
stored the RealClear rewrite (or display cleanup) as the title, so writers were
credited with headlines they did not write. This script fetches each article
page once, reads the publisher headline (curator.original_titles), and
records it in data/original_titles.json:

    {"urls": {url: {"title": str | null, "status": int | null,
                    "final_url": str, "via": "page" | "feed" | null,
                    "fetched_on": "YYYY-MM-DD"}}}

A page that cannot be read, or that redirects to a site's homepage or archive
(a dead link), keeps "title": null; those items are left off voice pages.

    python scripts/backfill_original_titles.py --fetch      # network, resumable
    python scripts/backfill_original_titles.py --feeds      # fill gaps from live feeds
    python scripts/backfill_original_titles.py --apply      # rewrite saved titles

--apply writes `original_title` into archive meta.json rows, article history
and yesterday.json, and replaces headline text on archive pages and the
digest page with the publisher headline (the archive and digest are not the
front page, so the rewrite does not belong there). Items whose headline could
not be recovered are left as they are and counted.

Pages are cached gzipped under /tmp/cc_pages so the byline pass can reparse
them without refetching (--page-cache to move it).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curator.original_titles import CACHE_PATH, extract_headline, publisher_title  # noqa: E402
from fetcher.rss_fetcher import USER_AGENT  # noqa: E402

DOCS = REPO_ROOT / "docs"
ARCHIVE = DOCS / "archive"
HISTORY = DOCS / "article_history.json"
YESTERDAY = DOCS / "yesterday.json"
DIGEST = DOCS / "digest" / "index.html"
DATA_WATCH = DOCS / "data_watch.json"

TITLE_LINK_RE = re.compile(
    r'(<a href="(https?://[^"]+)" class="cc-(?:lead-title|article-title|headline-title|headline-lead-title|world-news-title)"[^>]*>)(\s*)(.*?)(\s*)(</a>)',
    re.S)
GTAG_TITLE_RE = re.compile(r"('article_title':')([^']*)(')")
HEADERS = {"User-Agent": USER_AGENT,
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}


def page_cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html.gz")


def collect_urls() -> dict[str, str]:
    """url -> source name for every saved article (archive, history, yesterday)."""
    out: dict[str, str] = {}
    for day in sorted(ARCHIVE.iterdir()):
        meta = day / "meta.json"
        if meta.exists():
            for a in json.loads(meta.read_text(encoding="utf-8")).get("articles", []):
                if a.get("url"):
                    out.setdefault(a["url"], a.get("source", ""))
        idx = day / "index.html"
        if idx.exists():
            for m in TITLE_LINK_RE.finditer(idx.read_text(encoding="utf-8", errors="replace")):
                out.setdefault(m.group(2), "")
    for row in json.loads(HISTORY.read_text(encoding="utf-8")):
        if row.get("url"):
            out.setdefault(row["url"], row.get("source_name", ""))
    for row in json.loads(YESTERDAY.read_text(encoding="utf-8")):
        if row.get("url"):
            out.setdefault(row["url"], row.get("source_name", ""))
    for items in json.loads(DATA_WATCH.read_text(encoding="utf-8")).get("fresh", {}).values():
        for row in items:
            if row.get("url"):
                out.setdefault(row["url"], row.get("source", ""))
    return out


def load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"urls": {}}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache["urls"] = dict(sorted(cache["urls"].items()))
    CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def is_dead_redirect(url: str, final_url: str) -> bool:
    """A redirect to a homepage, a listing, or a different site is a dead link."""
    a, b = urlparse(url), urlparse(final_url)
    if not final_url or final_url == url:
        return False
    path = b.path.rstrip("/")
    if path in ("", "/blog", "/articles", "/news", "/category", "/posts"):
        return True
    host_a = a.netloc.lower().removeprefix("www.")
    host_b = b.netloc.lower().removeprefix("www.")
    feedish = host_a.startswith("feed") or host_a.startswith("feeds.")
    if host_a != host_b and not feedish and host_b.split(".")[-2:] != host_a.split(".")[-2:]:
        return True
    return False


def fetch_one(url: str, source: str, cache_dir: Path) -> dict:
    row = {"title": None, "status": None, "final_url": "", "via": None,
           "fetched_on": date.today().isoformat()}
    try:
        resp = requests.get(url, timeout=20, headers=HEADERS, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}"[:80]
        return row
    row["status"] = resp.status_code
    row["final_url"] = resp.url
    if resp.status_code >= 400 or resp.status_code == 202:
        return row
    text = resp.text
    page_cache_path(cache_dir, url).write_bytes(gzip.compress(text.encode("utf-8", "replace")))
    if is_dead_redirect(url, resp.url):
        row["error"] = "redirected"
        return row
    title = extract_headline(text, resp.url, source)
    if title and not re.search(r"just a moment|attention required|access denied|page not found|404",
                               title, re.I):
        row["title"] = title
        row["via"] = "page"
    return row


def run_fetch(cache_dir: Path, workers: int, retry_failed: bool) -> None:
    cache = load_cache()
    urls = collect_urls()
    todo = [u for u in urls if u not in cache["urls"]
            or (retry_failed and not cache["urls"][u].get("title"))]
    print(f"{len(urls)} saved article URLs, {len(todo)} to fetch")
    cache_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_one, u, urls[u], cache_dir): u for u in todo}
        for fut in as_completed(futs):
            cache["urls"][futs[fut]] = fut.result()
            done += 1
            if done % 200 == 0:
                save_cache(cache)
                print(f"  {done}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
    save_cache(cache)
    rows = cache["urls"].values()
    print(f"cached {len(cache['urls'])}: {sum(1 for r in rows if r.get('title'))} with a headline")


def run_reparse(cache_dir: Path) -> None:
    """Re-extract headlines from cached pages (after an extractor change)."""
    cache = load_cache()
    sources = collect_urls()
    n = 0
    for url, row in cache["urls"].items():
        if row.get("via") == "feed" or row.get("error") == "redirected":
            continue
        path = page_cache_path(cache_dir, url)
        if not path.exists():
            continue
        page = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
        title = extract_headline(page, row.get("final_url") or url, sources.get(url, "")) or None
        if title and re.search(r"just a moment|attention required|access denied|page not found|404",
                               title, re.I):
            title = None
        if title != row.get("title"):
            row["title"], row["via"] = title, ("page" if title else None)
            n += 1
    save_cache(cache)
    print(f"reparsed: {n} headlines changed")


def run_wayback(cache_dir: Path, workers: int) -> None:
    """Fill pages a site blocks (WORLD's bot challenge) from Wayback snapshots."""
    cache = load_cache()
    todo = [u for u, r in cache["urls"].items()
            if not r.get("title") and r.get("error") != "redirected" and r.get("status") != 404]

    def one(url):
        try:
            r = requests.get("https://archive.org/wayback/available", params={"url": url},
                             timeout=30).json()
            snap = (r.get("archived_snapshots") or {}).get("closest") or {}
            if not snap.get("available") or str(snap.get("status")) != "200":
                return url, None
            page = requests.get(snap["url"].replace("http://", "https://", 1), timeout=40,
                                headers=HEADERS).text
            return url, extract_headline(page, url) or None
        except Exception:  # noqa: BLE001
            return url, None

    found = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for url, title in pool.map(one, todo):
            if title and not re.search(r"just a moment|attention required|page not found|404|wayback",
                                       title, re.I):
                cache["urls"][url].update(title=title, via="wayback")
                found += 1
    save_cache(cache)
    print(f"wayback: {found} of {len(todo)} recovered")


def run_feeds() -> None:
    """Fill unrecovered rows from the live feeds (recent items only)."""
    import feedparser
    from fetcher.sources import SOURCES

    cache = load_cache()
    missing = {u for u, r in cache["urls"].items() if not r.get("title")}
    found = 0

    def one(src):
        try:
            resp = requests.get(src["url"], timeout=20, headers={"User-Agent": USER_AGENT})
            return src, feedparser.parse(resp.content)
        except Exception:  # noqa: BLE001
            return src, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        for src, feed in pool.map(one, [s for s in SOURCES if s.get("url")]):
            if not feed:
                continue
            for e in feed.entries:
                link = e.get("link", "")
                if link in missing and e.get("title"):
                    r = cache["urls"][link]
                    r["title"] = " ".join(e.title.split())
                    r["via"] = "feed"
                    missing.discard(link)
                    found += 1
    save_cache(cache)
    print(f"filled {found} from live feeds; {len(missing)} still unrecovered")


def _replace_titles(page: str, titles: dict[str, str]) -> tuple[str, int]:
    """Swap headline text in archive / digest markup for the publisher's."""
    n = 0

    def link(m):
        nonlocal n
        url = m.group(2)
        t = titles.get(url)
        if not t:
            return m.group(0)
        new = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        open_tag = GTAG_TITLE_RE.sub(lambda g: g.group(1) + t.replace("'", "").replace("&", "&amp;")
                                     .replace('"', "&quot;") + g.group(3), m.group(1))
        if new == m.group(4).strip() and open_tag == m.group(1):
            return m.group(0)
        n += 1
        return open_tag + m.group(3) + new + m.group(5) + m.group(6)

    return TITLE_LINK_RE.sub(link, page), n


def run_apply() -> None:
    cache = load_cache()["urls"]
    titles: dict[str, str] = {}
    for u, r in cache.items():
        if r.get("title"):
            titles[u] = publisher_title(r["title"], "", r.get("final_url") or u)

    pages = changed_links = 0
    for day in sorted(ARCHIVE.iterdir()):
        idx = day / "index.html"
        if idx.exists():
            h = idx.read_text(encoding="utf-8")
            out, n = _replace_titles(h, titles)
            if out != h:
                idx.write_text(out, encoding="utf-8")
                pages += 1
                changed_links += n
        meta = day / "meta.json"
        if meta.exists():
            d = json.loads(meta.read_text(encoding="utf-8"))
            dirty = False
            for a in d.get("articles", []):
                t = titles.get(a.get("url", ""))
                if t and a.get("original_title") != t:
                    a["original_title"] = t
                    dirty = True
            if dirty:
                meta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(f"archive pages: {pages} changed, {changed_links} headlines replaced")

    if DIGEST.exists():
        h = DIGEST.read_text(encoding="utf-8")
        out, n = _replace_titles(h, titles)
        if out != h:
            DIGEST.write_text(out, encoding="utf-8")
        print(f"digest: {n} headlines replaced")

    watch = json.loads(DATA_WATCH.read_text(encoding="utf-8"))
    k = 0
    for items in watch.get("fresh", {}).values():
        for r in items:
            t = titles.get(r.get("url", ""))
            if t and r.get("title") != t:
                r["title"] = t
                k += 1
    DATA_WATCH.write_text(json.dumps(watch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"data_watch.json: {k} fresh titles set to the publisher headline")

    for path in (HISTORY, YESTERDAY):
        rows = json.loads(path.read_text(encoding="utf-8"))
        k = 0
        for r in rows:
            t = titles.get(r.get("url", ""))
            if t and r.get("original_title") != t:
                r["original_title"] = t
                k += 1
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{path.name}: original_title set on {k} rows")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--reparse", action="store_true")
    ap.add_argument("--feeds", action="store_true")
    ap.add_argument("--wayback", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--page-cache", default="/tmp/cc_pages")
    args = ap.parse_args(argv)
    if args.fetch:
        run_fetch(Path(args.page_cache), args.workers, args.retry_failed)
    if args.reparse:
        run_reparse(Path(args.page_cache))
    if args.feeds:
        run_feeds()
    if args.wayback:
        run_wayback(Path(args.page_cache), min(args.workers, 6))
    if args.apply:
        run_apply()
    return 0


if __name__ == "__main__":
    sys.exit(main())
