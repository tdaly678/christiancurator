"""
discovery.py: the discovery queue (P2.3, 2026-10-30).

Discovery sources (role "discovery", or items matching a source's
discovery_title_pattern) are never ranked themselves. Some of them are link
roundups that point at good pieces outside our feed list. This module turns
those outbound links into ordinary candidate articles.

Flow, once per run (main.py, right after fetch_all):
  1. harvest_links(): for discovery items from sources that opt in with
     `harvest_links: True` (every discovery item) or a
     `discovery_harvest_pattern` regex on the title (Tim Challies' A La
     Carte), pull outbound <a href> links from the feed HTML. Links to the
     roundup's own site, stores, social sites, images, homepages and short
     anchor texts (fewer than 3 words: "Download", "here") are dropped.
  2. The links join the queue in docs/discovery_queue.json, keyed by
     canonical URL. Entries already shown (article_history) are skipped.
  3. graduate(): up to MAX_FETCH_PER_RUN pending entries are fetched; the
     page's og:title / description / site name / author / published time
     become a normal article dict (role "primary", `discovered_via` set to the
     roundup source). These go into score_articles() with everything else,
     so Claude scores them and dedup collapses them against feed copies.
     Graduated entries are marked status "graduated"; pages that fail twice
     are "failed". Entries older than QUEUE_TTL_DAYS are pruned.

The Aquila Report is a discovery source too, but its feed carries no link to
the original and its item pages sit behind a Cloudflare challenge, so it does
not opt in to harvesting yet.
"""

from __future__ import annotations

import html as htmllib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

from curator.dedup import canonical_url
from .sources import SOURCES

QUEUE_PATH = Path(__file__).parent.parent / "docs" / "discovery_queue.json"
MAX_FETCH_PER_RUN = 25
MAX_ATTEMPTS = 2
QUEUE_TTL_DAYS = 7
MAX_ITEM_AGE_DAYS = 3        # only harvest roundups published this recently
MIN_ANCHOR_WORDS = 3
FETCH_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 ChristianCurator/1.0 "
    "(+https://www.christiancurator.com/)"
)

SKIP_DOMAINS = {
    "christiancurator.com", "amazon.com", "amzn.to", "amazon.ca", "churchsource.com",
    "christianbook.com", "wtsbooks.com", "logos.com", "faithlife.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com", "threads.net", "tiktok.com",
    "youtube.com", "youtu.be", "vimeo.com", "podcasts.apple.com", "open.spotify.com",
    "bit.ly", "feedburner.com", "squarequotes.church",
}
SKIP_SUBDOMAIN_PREFIXES = ("store.", "shop.", "grow.", "gift.")
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".mp3", ".mp4", ".zip")

_SOURCES_BY_NAME = {s["name"]: s for s in SOURCES}


def _base_domain(host: str) -> str:
    labels = [l for l in (host or "").lower().split(":")[0].split(".") if l]
    return ".".join(labels[-2:]) if len(labels) >= 2 else ".".join(labels)


_SOURCE_BY_DOMAIN = {}
for _s in SOURCES:
    _d = _base_domain(urlsplit(_s["url"]).hostname or "")
    # Shared hosts (substack.com, medium.com) can't identify a source.
    if _d and _d not in ("substack.com", "medium.com", "wordpress.com", "blogspot.com"):
        _SOURCE_BY_DOMAIN.setdefault(_d, _s)


# ------------------------------------------------------------------ harvesting

def _harvests(source: dict, title: str) -> bool:
    if source.get("harvest_links"):
        return True
    pattern = source.get("discovery_harvest_pattern")
    return bool(pattern and re.search(pattern, title or "", re.IGNORECASE))


def _clean_text(s: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def keep_link(url: str, anchor: str, roundup_domain: str) -> bool:
    """True when an outbound link looks like an article worth queueing."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return False
    domain = _base_domain(host)
    if domain == roundup_domain or domain in SKIP_DOMAINS or host in SKIP_DOMAINS:
        return False
    if host.startswith(SKIP_SUBDOMAIN_PREFIXES):
        return False
    path = parts.path.rstrip("/")
    if not path or path.lower().endswith(SKIP_EXTENSIONS):
        return False
    if "utm_source=challies" in parts.query.lower():  # sponsor links
        return False
    return len(anchor.split()) >= MIN_ANCHOR_WORDS


def extract_links(item: dict) -> list[dict]:
    """Outbound article links from one discovery item's feed HTML."""
    body = item.get("full_content") or item.get("summary") or ""
    roundup_domain = _base_domain(urlsplit(item.get("url") or "").hostname or "")
    out, seen = [], set()
    for href, inner in re.findall(r'<a\s[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.S | re.I):
        url = htmllib.unescape(href).strip()
        anchor = _clean_text(inner).rstrip(".").strip()
        canon = canonical_url(url)
        if canon in seen or not keep_link(url, anchor, roundup_domain):
            continue
        seen.add(canon)
        out.append({"url": url, "canonical_url": canon, "anchor": anchor})
    return out


def _item_age_days(item: dict, today: date) -> int | None:
    from email.utils import parsedate_to_datetime
    try:
        return (today - parsedate_to_datetime(item.get("published", "")).date()).days
    except (TypeError, ValueError):
        return None


def harvest_links(articles: list[dict], today: date | None = None) -> list[dict]:
    """Queue entries from this run's discovery items that opt in to harvesting."""
    today = today or date.today()
    entries = []
    for item in articles:
        if item.get("role") != "discovery":
            continue
        source = _SOURCES_BY_NAME.get(item.get("source_name", ""), {})
        if not _harvests(source, item.get("title", "")):
            continue
        age = _item_age_days(item, today)
        if age is not None and age > MAX_ITEM_AGE_DAYS:
            continue
        for link in extract_links(item):
            entries.append({**link, "found_via": item.get("source_name", ""),
                            "found_in": item.get("url", ""), "found_on": today.isoformat(),
                            "status": "pending", "attempts": 0})
    return entries


# ------------------------------------------------------------------ queue file

def load_queue(path: Path = QUEUE_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and "entries" in data else {"entries": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"entries": {}}


def save_queue(queue: dict, path: Path = QUEUE_PATH) -> None:
    queue["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=1, ensure_ascii=False)


def merge_into_queue(queue: dict, new_entries: list[dict], shown_urls: set,
                     today: date | None = None) -> int:
    """Add new entries (skipping known and already-shown URLs); prune old ones.

    Returns the number of entries added.
    """
    today = today or date.today()
    entries = queue.setdefault("entries", {})
    cutoff = (today - timedelta(days=QUEUE_TTL_DAYS)).isoformat()
    for key in [k for k, e in entries.items() if e.get("found_on", "") < cutoff]:
        del entries[key]
    shown_canon = {canonical_url(u) for u in shown_urls or ()}
    added = 0
    for e in new_entries:
        key = e["canonical_url"]
        if key in entries or key in shown_canon:
            continue
        entries[key] = e
        added += 1
    return added


# ------------------------------------------------------------------ graduation

def _meta(page: str, *names: str) -> str:
    for name in names:
        key = rf'(?:property|name|itemprop)=["\']{re.escape(name)}["\']'
        value = r'content=(?:"([^"]*)"|\'([^\']*)\')'
        for pat in (rf'<meta[^>]+{key}[^>]*?{value}', rf'<meta[^>]+{value}[^>]*{key}'):
            m = re.search(pat, page, re.I)
            found = m and (m.group(1) if m.group(1) is not None else m.group(2)) or ""
            if found.strip():
                return htmllib.unescape(found).strip()
    return ""


def _published(raw: str) -> str:
    """ISO 8601 meta date -> RFC 2822 (what the scorer parses), or ''."""
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _strip_site_suffix(title: str, site_names: set) -> str:
    """'Title - Christianity Today' -> 'Title'. Any ' | Short Tail' goes too."""
    m = re.match(r"^(.*\S)\s+([|\u2013\u2014-])\s+([^|\u2013\u2014]{1,40})$", title)
    if not m:
        return title
    head, sep, tail = m.groups()
    names = {n.lower() for n in site_names if n}
    return head if tail.strip().lower() in names or sep == "|" else title


def _author(page: str) -> str:
    """Byline from meta tags; profile URLs (article:author is often one) are dropped."""
    author = _meta(page, "author", "parsely-author", "article:author")
    return "" if author.lower().startswith(("http://", "https://")) else author


def article_from_page(entry: dict, page: str, final_url: str) -> dict | None:
    """Build a scorer-ready article dict from a fetched page, or None."""
    title = _meta(page, "og:title", "twitter:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        title = _clean_text(m.group(1)) if m else ""
    host = urlsplit(final_url).hostname or ""
    known = _SOURCE_BY_DOMAIN.get(_base_domain(host))
    if known and known.get("role") in ("discovery", "media"):
        return None
    og_site = _meta(page, "og:site_name")
    site_name = (known or {}).get("name") or og_site or _base_domain(host)
    title = _strip_site_suffix(title, {site_name, og_site})
    title = title or entry.get("anchor", "")
    if not title:
        return None
    description = _meta(page, "og:description", "description", "twitter:description")
    return {
        "source_name": site_name,
        "source_category": (known or {}).get("category", "culture"),
        "source_type": (known or {}).get("source_type", "christian"),
        "independent": (known or {}).get("independent", False),
        # Unknown sites must not spawn /voices/ pages from one linked piece.
        "creates_voices": bool(known) and known.get("creates_voices", True),
        "role": "primary",
        "author": _author(page),
        "title": title,
        "url": final_url,
        "summary": description,
        "full_content": "",
        "published": _published(_meta(page, "article:published_time", "datePublished",
                                      "parsely-pub-date")),
        "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "discovered_via": entry.get("found_via", ""),
        "discovered_in": entry.get("found_in", ""),
        "score": None,
        "tags": [],
        "rewritten_title": None,
    }


def _fetch(entry: dict) -> tuple[dict, dict | None, str]:
    try:
        resp = requests.get(entry["url"], timeout=FETCH_TIMEOUT, allow_redirects=True,
                            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    except Exception as exc:
        return entry, None, f"{type(exc).__name__}"
    if resp.status_code >= 400:
        return entry, None, f"HTTP {resp.status_code}"
    if "html" not in resp.headers.get("Content-Type", "html").lower():
        return entry, None, "not html"
    return entry, article_from_page(entry, resp.text[:400_000], resp.url), ""


def graduate(queue: dict, limit: int = MAX_FETCH_PER_RUN, fetch=_fetch) -> list[dict]:
    """Fetch up to `limit` pending entries; return article dicts for scoring."""
    pending = [e for e in queue.get("entries", {}).values() if e.get("status") == "pending"]
    pending.sort(key=lambda e: e.get("found_on", ""), reverse=True)
    batch = pending[:limit]
    if not batch:
        return []
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch, batch))
    today = date.today().isoformat()
    graduated = []
    for entry, article, error in results:
        entry["attempts"] = entry.get("attempts", 0) + 1
        if article:
            entry.update(status="graduated", graduated_on=today, title=article["title"],
                         source_name=article["source_name"])
            entry.pop("error", None)
            graduated.append(article)
        else:
            entry["error"] = error or "no title"
            if entry["attempts"] >= MAX_ATTEMPTS:
                entry["status"] = "failed"
    return graduated


def run_discovery_queue(articles: list[dict], shown_urls: set) -> list[dict]:
    """Harvest, queue and graduate. Returns new candidate articles for scoring."""
    queue = load_queue()
    added = merge_into_queue(queue, harvest_links(articles), shown_urls)
    graduated = graduate(queue)
    save_queue(queue)
    pending = sum(1 for e in queue["entries"].values() if e.get("status") == "pending")
    print(f"  Discovery queue: +{added} links, {len(graduated)} graduated to scoring, {pending} pending.")
    return graduated
