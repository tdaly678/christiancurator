"""
dedup.py: cross-feed canonical dedup, run before ranking.

The same piece can arrive from several feeds: an aggregator repost, a
publisher's second feed, a syndication partner, or the same link carrying
different tracking params. score_articles() calls dedupe_articles() first so
one story can never take two slots on the front page.

Two passes:
  1. Canonical URL: https, no www, no tracking params, no fragment, no
     trailing slash, remaining query params sorted.
  2. Normalized title (only titles of DEDUP_TITLE_MIN_CHARS or more, so short
     generic titles like "Weekend Links" never collide).

Within a duplicate group the survivor is chosen by:
  primary role over discovery, then the copy whose source domain matches the
  link domain (the original publisher), then christian over world_news, then
  feed order (sources.py order, which fetch_all preserves).
The losing sources are recorded on the survivor as `also_from`.
"""

import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from fetcher.sources import SOURCES

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "ref", "ref_src", "ref_url", "cmpid", "_hsenc", "_hsmi", "mkt_tok",
    "rss", "feed", "share", "via",
}
TRACKING_PREFIXES = ("utm_", "pk_", "hsa_")
DEDUP_TITLE_MIN_CHARS = 25


def canonical_url(url: str) -> str:
    """Normalize a URL for identity comparison. Not for display or linking."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = re.sub(r"/{2,}", "/", parts.path or "").rstrip("/")
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    )
    return urlunsplit(("https", host, path, urlencode(query), ""))


def _base_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0]
    labels = [l for l in host.split(".") if l]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


_SOURCE_DOMAINS = {s["name"]: _base_domain(urlsplit(s["url"]).hostname or "") for s in SOURCES}
_SOURCE_ORDER = {s["name"]: i for i, s in enumerate(SOURCES)}


def _title_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9 ]+", "", (title or "").lower())
    key = re.sub(r"\s+", " ", key).strip()
    return key if len(key) >= DEDUP_TITLE_MIN_CHARS else ""


def _preference(article: dict) -> tuple:
    """Lower sorts first = preferred survivor."""
    link_domain = _base_domain(urlsplit(article.get("url") or "").hostname or "")
    own_domain = _SOURCE_DOMAINS.get(article.get("source_name", ""))
    return (
        0 if article.get("role", "primary") == "primary" else 1,
        0 if own_domain and own_domain == link_domain else 1,
        0 if article.get("source_type") != "world_news" else 1,
        _SOURCE_ORDER.get(article.get("source_name", ""), len(_SOURCE_ORDER)),
    )


def _collapse(articles: list[dict], key_fn) -> tuple[list[dict], int]:
    groups: dict[str, list[dict]] = {}
    order: list = []
    for a in articles:
        k = key_fn(a)
        if not k:
            order.append(a)
            continue
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(a)

    out, removed = [], 0
    for item in order:
        if isinstance(item, dict):
            out.append(item)
            continue
        group = groups[item]
        survivor = min(group, key=_preference)
        for loser in group:
            if loser is survivor:
                continue
            removed += 1
            names = [loser.get("source_name", "")] + loser.get("also_from", [])
            for n in names:
                if n and n != survivor.get("source_name") and n not in survivor.get("also_from", []):
                    survivor.setdefault("also_from", []).append(n)
        out.append(survivor)
    return out, removed


def dedupe_articles(articles: list[dict]) -> list[dict]:
    """Collapse cross-feed duplicates. Sets `canonical_url` on every article."""
    for a in articles:
        a["canonical_url"] = canonical_url(a.get("url", ""))
    articles, by_url = _collapse(articles, lambda a: a["canonical_url"])
    articles, by_title = _collapse(articles, lambda a: _title_key(a.get("title", "")))
    if by_url or by_title:
        print(f"  Canonical dedup: removed {by_url} same-URL and {by_title} same-title duplicates.")
    return articles
