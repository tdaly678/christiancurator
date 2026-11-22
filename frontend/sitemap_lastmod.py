"""Honest sitemap <lastmod> values (S1 report, section 6).

Every URL used to get today's date (or the file mtime, which on a fresh
runner checkout is also today), which teaches Google to ignore lastmod.

Rule, per page:
1. The page's own ``dateModified`` (JSON-LD, or ``article:modified_time``)
   when it has one. Topic pages and the pilot voice pages carry it.
2. Otherwise the date its content last changed. ``content_fingerprint()``
   hashes the visible main text (head, nav, header, footer, scripts, styles
   and comments removed), so site-wide markup sweeps (CSS, nav, favicon) do
   not count as a change. ``LastmodState`` keeps ``{url: [fingerprint, date]}``
   in data/sitemap_lastmod.json (committed by the daily run with data/): an
   unchanged fingerprint keeps its date, a new or changed one gets today.

scripts/seed_sitemap_lastmod.py seeds the state from git history (the date of
the last commit that changed each page's fingerprint), because the daily run
uses a shallow checkout.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_DATE_MODIFIED_RE = re.compile(r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})')
_META_MODIFIED_RE = re.compile(
    r'<meta[^>]+(?:property|name)="article:modified_time"[^>]+content="(\d{4}-\d{2}-\d{2})'
    r'|<meta[^>]+content="(\d{4}-\d{2}-\d{2})[^"]*"[^>]+(?:property|name)="article:modified_time"')
_STRIP_BLOCKS_RE = re.compile(
    r"<(script|style|nav|header|footer|noscript|svg)\b.*?</\1\s*>", re.S | re.I)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def date_modified(html: str) -> str | None:
    """The page's own dateModified (YYYY-MM-DD), if it declares one."""
    m = _DATE_MODIFIED_RE.search(html)
    if m:
        return m.group(1)
    m = _META_MODIFIED_RE.search(html)
    if m:
        return m.group(1) or m.group(2)
    return None


def content_fingerprint(html: str) -> str:
    """Hash of the page's visible body text, ignoring chrome and markup."""
    end = html.find("</head>")
    body = html[end:] if end >= 0 else html
    body = _COMMENT_RE.sub(" ", body)
    body = _STRIP_BLOCKS_RE.sub(" ", body)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", body)).strip()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


class LastmodState:
    """{url: [fingerprint, date]} persisted as JSON."""

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        self.seen: set[str] = set()

    def lastmod(self, url: str, html: str, today: str) -> str:
        self.seen.add(url)
        fp = content_fingerprint(html)
        prev = self.data.get(url)
        if prev and prev[0] == fp:
            date = prev[1]
        else:
            date = today
        dm = date_modified(html)
        self.data[url] = [fp, date]
        return dm or date

    def save(self) -> None:
        data = {u: v for u, v in sorted(self.data.items()) if u in self.seen}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=0, sort_keys=True) + "\n", encoding="utf-8")
