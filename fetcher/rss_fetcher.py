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
            articles.append({
                "source_name": source["name"],
                "source_category": source["category"],
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
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
