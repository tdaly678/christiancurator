"""
rss_fetcher.py — fetches and normalizes articles from RSS feeds using feedparser.
"""

import feedparser
from datetime import datetime
from .sources import SOURCES

MAX_ARTICLES_PER_SOURCE = 20  # only take the most recent articles per feed


def fetch_feed(source: dict) -> list[dict]:
    """Fetch and parse a single RSS feed. Returns a list of article dicts."""
    print(f"  Fetching: {source['name']} ({source['url']})")
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        for entry in feed.entries[:MAX_ARTICLES_PER_SOURCE]:
            # Extract author — prefer entry-level, fall back to feed-level
            author = (
                entry.get("author")
                or getattr(entry.get("author_detail"), "name", None)
                or feed.feed.get("author")
                or ""
            ).strip()
            # Capture full article body from content:encoded if available.
            # feedparser stores this in entry.content[0].value.
            # Used by the large feature card to show a 3-4 sentence preview.
            content_list = entry.get("content", [])
            full_content = content_list[0].get("value", "") if content_list else ""

            articles.append({
                "source_name": source["name"],
                "source_category": source["category"],
                "source_type": source.get("source_type", "christian"),
                "independent": source.get("independent", False),
                "author": author,
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "full_content": full_content,
                "published": entry.get("published", ""),
                "fetched_at": datetime.utcnow().isoformat(),
                # Curator fields (populated later)
                "score": None,
                "tags": [],
                "rewritten_title": None,
            })
        return articles
    except Exception as e:
        print(f"  ERROR fetching {source['name']}: {e}")
        return []


def fetch_all() -> list[dict]:
    """Fetch all sources and return a flat list of articles."""
    all_articles = []
    for source in SOURCES:
        articles = fetch_feed(source)
        all_articles.extend(articles)
    return all_articles
