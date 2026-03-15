"""
sources.py — seed list of Christian RSS feeds.

Add or remove sources here. Each entry is a dict with:
  - name:     human-readable source name
  - url:      RSS feed URL
  - category: broad topic tag (e.g. "theology", "culture", "missions")
"""

SOURCES = [
    {
        "name": "The Gospel Coalition",
        "url": "https://www.thegospelcoalition.org/feed/",
        "category": "theology",
    },
    {
        "name": "Christianity Today",
        "url": "https://www.christianitytoday.com/feed",
        "category": "culture",
    },
    {
        "name": "Desiring God",
        "url": "https://feed.desiringgod.org/articles-by-desiring-god.rss",
        "category": "theology",
    },
    {
        "name": "World Magazine",
        "url": "https://wng.org/feeds/rss/topics.rss",
        "category": "news",
    },
    {
        "name": "Relevant Magazine",
        "url": "https://relevantmagazine.com/feed/",
        "category": "culture",
    },
    # Add more sources here
]
