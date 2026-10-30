"""
rss_fetcher.py — fetches and normalizes articles from RSS feeds.

Each feed is downloaded with requests (timeout + browser User-Agent, since some
CDNs block feedparser's default UA) and the bytes are handed to feedparser.
Feeds are fetched in a small thread pool so one slow host can't stall the run.

Every run writes per-source health to docs/feed_health.json:

    {
      "run_at": "...",
      "sources": [{source, url, role, http_status, n_entries, newest_date,
                   bozo, stale, error?}, ...],
      "zero_streaks": {source: {"since": "YYYY-MM-DD",
                                "last_date": "YYYY-MM-DD", "days": N}}
    }

`zero_streaks` is the history: a source that returns 0 items (or errors) on N
distinct run days in a row has days == N. The daily workflow commits the file
and scripts/check_feed_health.py fails the run once any streak reaches
ZERO_STREAK_FAIL_DAYS, after the site has already been published.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import feedparser
import requests

from .sources import SOURCES

MAX_ARTICLES_PER_SOURCE = 20  # only take the most recent articles per feed
FETCH_TIMEOUT = 15            # seconds per feed
FETCH_WORKERS = 8
STALE_FEED_DAYS = 60          # newest item older than this is flagged "stale"
ZERO_STREAK_FAIL_DAYS = 7     # read by scripts/check_feed_health.py

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 ChristianCurator/1.0 "
    "(+https://www.christiancurator.com/)"
)
# Some sites do the opposite of a CDN block: Ligonier serves its HTML homepage
# to browser UAs and the XML feed only to feed readers. When the browser UA
# yields no items, retry once as a feed reader.
READER_USER_AGENT = "ChristianCurator/1.0 (+https://www.christiancurator.com/) feedparser/6"
ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"

FEED_HEALTH_PATH = Path(__file__).parent.parent / "docs" / "feed_health.json"

# Matches an email address (used to normalize RSS bylines like
# "jakemeador@gmail.com (Jake Meador)" or bare "jpanyard@christianitytoday.com").
_EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def clean_author(raw: str) -> str:
    """Normalize an RSS author byline.

    Some feeds (RSS 2.0 <author>) provide "email@example.com (Real Name)" —
    extract "Real Name". Bare emails with no name yield "" so junk
    email-derived voice slugs never get generated downstream.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    # "email@example.com (Real Name)" -> "Real Name"
    m = re.fullmatch(_EMAIL_RE + r"\s*\((.+?)\)", raw)
    if m:
        return m.group(1).strip()
    # Strip any embedded email addresses; a bare email becomes "".
    cleaned = re.sub(_EMAIL_RE, "", raw)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \t,;:()-")
    return cleaned


def _entry_datetime(entry) -> datetime | None:
    """Best publish time for an entry: published_parsed, then updated_parsed."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _entry_published(entry, dt: datetime | None) -> str:
    """RFC 2822 date string for the scorer's 30-day cutoff.

    The scorer parses `published` with parsedate_to_datetime, which can't read
    Atom/ISO dates and silently keeps items with an empty string. Normalizing
    from the parsed struct means every dated item gets the cutoff.
    """
    if dt is not None:
        return format_datetime(dt)
    return entry.get("published") or entry.get("updated") or ""


def parse_duration(raw) -> int | None:
    """Seconds from an itunes:duration value ("3591", "26:24", "01:33:02")."""
    raw = str(raw or "").strip()
    if not raw:
        return None
    try:
        secs = 0
        for part in raw.split(":"):
            secs = secs * 60 + int(float(part))
        return secs or None
    except ValueError:
        return None


APPLE_LOOKUP_URL = "https://itunes.apple.com/lookup"


def apple_episode_urls(apple_id, timeout: int = FETCH_TIMEOUT) -> dict[str, str]:
    """{episode guid: Apple Podcasts episode URL} for one show, or {} on failure.

    Many podcast feeds give every episode the show's homepage as its link, or no
    link at all. The Watch and Listen lane needs a page for the episode itself,
    and Apple's episode pages play in any browser.
    """
    try:
        resp = requests.get(APPLE_LOOKUP_URL, timeout=timeout, params={
            "id": apple_id, "entity": "podcastEpisode", "limit": 50})
        results = resp.json().get("results", [])
    except Exception:
        return {}
    return {r["episodeGuid"]: r["trackViewUrl"].replace("&uo=4", "")
            for r in results if r.get("episodeGuid") and r.get("trackViewUrl")}


def _generic_links(feed) -> set[str]:
    """Entry links that are not episode-specific: the channel link, or any link
    shared by several entries (e.g. every episode pointing at the show page)."""
    seen, shared = set(), set()
    for e in feed.entries:
        link = e.get("link", "")
        (shared if link in seen else seen).add(link)
    channel = feed.feed.get("link")
    return shared | ({channel} if channel else set()) | {""}


def _article_role(source: dict, title: str) -> str:
    role = source.get("role", "primary")
    pattern = source.get("discovery_title_pattern")
    if role == "primary" and pattern and re.search(pattern, title, re.IGNORECASE):
        return "discovery"
    return role


def fetch_feed(source: dict) -> tuple[list[dict], dict]:
    """Fetch and parse a single RSS feed. Returns (articles, health)."""
    health = {
        "source": source["name"],
        "url": source["url"],
        "role": source.get("role", "primary"),
        "http_status": None,
        "n_entries": 0,
        "newest_date": None,
        "bozo": False,
    }
    feed = None
    for ua in (USER_AGENT, READER_USER_AGENT):
        health.pop("error", None)
        try:
            resp = requests.get(source["url"], timeout=FETCH_TIMEOUT,
                                headers={"User-Agent": ua, "Accept": ACCEPT})
        except Exception as e:
            health["error"] = f"{type(e).__name__}: {e}"[:300]
            return [], health
        health["http_status"] = resp.status_code
        if resp.status_code >= 400:
            health["error"] = f"HTTP {resp.status_code}"
            feed = None
            continue
        feed = feedparser.parse(resp.content)
        if feed.entries:
            if ua is READER_USER_AGENT:
                health["user_agent"] = "reader"
            break
    if feed is None:
        return [], health

    health["bozo"] = bool(feed.bozo)
    if feed.bozo and not feed.entries:
        health["error"] = f"parse error: {feed.get('bozo_exception')}"[:300]
    health["n_entries"] = len(feed.entries)

    newest = None
    articles = []
    fetched_at = datetime.utcnow().isoformat()
    for entry in feed.entries:
        dt = _entry_datetime(entry)
        if dt and (newest is None or dt > newest):
            newest = dt
    is_media = source.get("role") == "media"
    # Podcast feeds without episode pages: swap in Apple Podcasts episode URLs.
    # Episodes that still have no page get url "" and never reach the lane.
    generic, apple = set(), {}
    if is_media and source.get("apple_podcast_id"):
        generic = _generic_links(feed)
        if any(e.get("link", "") in generic for e in feed.entries[:MAX_ARTICLES_PER_SOURCE]):
            apple = apple_episode_urls(source["apple_podcast_id"])
            health["apple_episode_urls"] = len(apple)
    for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
        # YouTube channel feeds mix in Shorts; the media lane wants full videos.
        if is_media and "/shorts/" in entry.get("link", ""):
            continue
        dt = _entry_datetime(entry)
        # Extract author — prefer entry-level, fall back to feed-level
        author = clean_author(
            entry.get("author")
            or getattr(entry.get("author_detail"), "name", None)
            or feed.feed.get("author")
            or ""
        )
        # Capture full article body from content:encoded if available.
        # feedparser stores this in entry.content[0].value.
        # Used by the large feature card to show a 3-4 sentence preview.
        content_list = entry.get("content", [])
        full_content = content_list[0].get("value", "") if content_list else ""
        title = entry.get("title", "").strip()

        url = entry.get("link", "")
        if url in generic:
            url = apple.get(entry.get("id", ""), "")
        media_fields = {}
        if is_media:
            media_fields = {
                "media_format": source.get("media_format", "podcast"),
                "duration_seconds": parse_duration(entry.get("itunes_duration")),
            }
        articles.append({
            **media_fields,
            "source_name": source["name"],
            "source_category": source["category"],
            "source_type": source.get("source_type", "christian"),
            "independent": source.get("independent", False),
            "creates_voices": source.get("creates_voices", True),
            "role": _article_role(source, title),
            "author": author,
            "title": title,
            "url": url,
            "summary": entry.get("summary", ""),
            "full_content": full_content,
            "published": _entry_published(entry, dt),
            "fetched_at": fetched_at,
            # Curator fields (populated later)
            "score": None,
            "tags": [],
            "rewritten_title": None,
        })

    if newest:
        health["newest_date"] = newest.date().isoformat()
        health["stale"] = (datetime.now(timezone.utc) - newest).days > STALE_FEED_DAYS
    return articles, health


def write_feed_health(health: list[dict], path: Path = FEED_HEALTH_PATH) -> dict:
    """Write this run's health plus the rolling zero-item streaks."""
    today = date.today().isoformat()
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}
    old_streaks = previous.get("zero_streaks", {})

    streaks = {}
    for h in health:
        name = h["source"]
        if h["n_entries"] > 0:
            continue
        prev = old_streaks.get(name)
        if prev and prev.get("last_date") == today:
            streaks[name] = prev  # re-run on the same day: don't double count
        elif prev:
            streaks[name] = {"since": prev["since"], "last_date": today, "days": prev["days"] + 1}
        else:
            streaks[name] = {"since": today, "last_date": today, "days": 1}

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": health,
        "zero_streaks": streaks,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def fetch_all() -> list[dict]:
    """Fetch all sources in parallel and return a flat list of articles.

    Source order is preserved so downstream tie-breaking is unchanged.
    """
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        results = list(pool.map(fetch_feed, SOURCES))

    all_articles = []
    health = []
    for articles, h in results:
        all_articles.extend(articles)
        health.append(h)
        status = h.get("error") or f"{h['n_entries']} items, newest {h['newest_date']}"
        print(f"  {'OK  ' if h['n_entries'] else 'FAIL'} {h['source']}: {status}")

    try:
        report = write_feed_health(health)
        empty = [h["source"] for h in health if not h["n_entries"]]
        if empty:
            print(f"  WARNING: {len(empty)} feed(s) returned 0 items: {', '.join(empty)}")
        long_dead = {k: v["days"] for k, v in report["zero_streaks"].items()
                     if v["days"] >= ZERO_STREAK_FAIL_DAYS}
        if long_dead:
            print(f"  WARNING: feeds empty for {ZERO_STREAK_FAIL_DAYS}+ days: {long_dead}")
    except Exception as e:
        print(f"  (feed health log skipped: {e})")
    return all_articles
