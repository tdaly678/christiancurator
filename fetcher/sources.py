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
        "url": "https://www.christianitytoday.com/ct/channel/rss.xml",
        "category": "culture",
    },
    {
        "name": "Desiring God",
        "url": "https://www.desiringgod.org/articles.rss",
        "category": "theology",
    },
    {
        "name": "World Magazine",
        "url": "https://wng.org/feed",
        "category": "news",
    },
    {
        "name": "Relevant Magazine",
        "url": "https://relevantmagazine.com/feed/",
        "category": "culture",
    },
    # Add more sources here
]
