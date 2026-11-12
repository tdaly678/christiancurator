"""Publisher headlines for pages shown under a writer's byline.

The RealClear title rewrite (curator/title_rewriter.py, CC_REWRITE_TITLES=1) is
for the front page and the email only. Anywhere a headline sits under a real
person's name (voice pages, Recent Articles blocks, archive and digest pages,
topic pages) the publisher's own headline is shown instead.

Going forward every article carries `original_title` (set at ingest in
fetcher/rss_fetcher.py) and the saved rows (archive meta.json,
article_history.json, yesterday.json) store it next to the display title.
For rows saved before Nov 12 2026 the publisher headline was recovered from the
article pages by scripts/backfill_original_titles.py into
data/original_titles.json; `lookup()` reads that file.

`publisher_title()` is the only cleanup applied for display: whitespace,
HTML entities, a trailing " | Outlet" / " - Outlet" site tail, and dashes
(the site never ships em or en dashes). It never adds or swaps words.
"""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data" / "original_titles.json"

_LD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_HEADLINE_RE = re.compile(r'"headline"\s*:\s*"((?:[^"\\]|\\.)*)"')
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAIL_RE = re.compile(r"\s+(?:\||[-–—:·•])\s+([^|\-–—:·•]{2,60})$")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _meta(page: str, name: str) -> str:
    key = rf'(?:property|name)=["\']{re.escape(name)}["\']'
    value = r'content=(?:"([^"]*)"|\'([^\']*)\')'
    for pat in (rf'<meta[^>]+{key}[^>]*?{value}', rf'<meta[^>]+{value}[^>]*{key}'):
        m = re.search(pat, page, re.I)
        found = m and (m.group(1) if m.group(1) is not None else m.group(2)) or ""
        if found.strip():
            return html.unescape(found).strip()
    return ""


def _ld_headline(page: str) -> str:
    for block in _LD_RE.findall(page):
        m = _HEADLINE_RE.search(block)
        if m:
            try:
                return html.unescape(json.loads(f'"{m.group(1)}"')).strip()
            except ValueError:
                return html.unescape(m.group(1)).strip()
    return ""


def site_names(url: str, extra: tuple[str, ...] = ()) -> set[str]:
    """Normalized names a site tail may use: the domain and given names."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    names = {_norm(host), _norm(host.split(".")[0])}
    names |= {_norm(e) for e in extra if e}
    names.discard("")
    return names


def strip_site_tail(title: str, names: set[str]) -> str:
    """Drop one trailing " | Site" / " - Site" when Site is a known site name."""
    m = _TAIL_RE.search(title or "")
    if not m:
        return title
    tail = _norm(m.group(1))
    head = title[:m.start()].strip()
    if len(head.split()) >= 2 and tail and (
            tail in names or any(tail.startswith(n) or n.startswith(tail) for n in names if len(n) >= 4)
            or re.search(r"\.(com|org|net|co|fyi)$", m.group(1).strip(), re.I)):
        return head
    return title


def extract_headline(page: str, url: str, source: str = "") -> str:
    """The publisher headline on an article page, or "" when none is found.

    JSON-LD `headline` first (the post title on WordPress / Yoast sites),
    then og:title, twitter:title, and the <title> tag, each with a site tail
    removed.
    """
    names = site_names(url, (source, _meta(page, "og:site_name"),
                             _meta(page, "application-name")))
    candidates = [_ld_headline(page), _meta(page, "og:title"), _meta(page, "twitter:title")]
    m = _TITLE_TAG_RE.search(page)
    if m:
        candidates.append(html.unescape(re.sub(r"\s+", " ", m.group(1))).strip())
    for cand in candidates:
        cand = " ".join((cand or "").split())
        if not cand:
            continue
        cand = strip_site_tail(cand, names)
        if _norm(cand) in names or len(cand) < 4:
            continue
        # "Pew Research Center | Nonpartisan, ..." is a homepage title.
        lead = re.match(r"^(.+?)\s+[|\-–—:]\s+", cand)
        if lead and (_norm(lead.group(1)) in names
                     or any(_norm(lead.group(1)).startswith(n) for n in names if len(n) >= 4)):
            continue
        return cand
    return ""


def publisher_title(title: str, source: str = "", url: str = "") -> str:
    """Display form of a publisher headline: whitespace, entities, a site
    tail and dashes only. Never adds or swaps words."""
    from curator.headline_voice import strip_dashes

    t = " ".join(html.unescape(title or "").split())
    if url or source:
        t = strip_site_tail(t, site_names(url or "https://x.invalid/", (source,)))
    return strip_dashes(t).strip()


@lru_cache(maxsize=1)
def _cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8")).get("urls", {})
    except (OSError, ValueError):
        return {}


def lookup(url: str) -> str | None:
    """Recovered publisher headline for a pre-Nov 12 row, or None."""
    row = _cache().get(url or "")
    return (row or {}).get("title") or None


def article_original_title(a: dict) -> str:
    """Publisher headline for an article dict or saved row.

    Pipeline articles keep the feed headline in `title` (rewrites go to
    `rewritten_title`); saved rows carry it as `original_title`.
    """
    return a.get("original_title") or lookup(a.get("url", "")) or (
        a.get("title", "") if "rewritten_title" in a or "original_title" in a else "")


def byline_title(a: dict) -> str:
    """Headline to show under a byline (archive, digest, voice and topic
    pages): the publisher's, in display form. Falls back to the saved title
    only when no publisher headline is known."""
    t = article_original_title(a) or a.get("title") or ""
    return publisher_title(t, a.get("source_name") or a.get("source") or "", a.get("url") or "")
