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

    # ── Theology & Ministry ──
    {
        "name": "Ligonier Ministries",
        "url": "https://www.ligonier.org/feed/",
        "category": "theology",
    },
    {
        "name": "9Marks",
        "url": "https://www.9marks.org/feed/",
        "category": "church life",
    },
    {
        "name": "Crossway",
        "url": "https://www.crossway.org/articles/feed/",
        "category": "theology",
    },

    # ── Culture & Public Theology ──
    {
        "name": "American Reformer",
        "url": "https://americanreformer.org/feed/",
        "category": "culture",
    },
    {
        "name": "First Things",
        "url": "https://www.firstthings.com/rss",
        "category": "culture",
    },
    {
        "name": "Mere Orthodoxy",
        "url": "https://mereorthodoxy.com/feed/",
        "category": "culture",
    },
    {
        "name": "Reformation21",
        "url": "https://www.reformation21.org/feed/",
        "category": "theology",
    },

    # ── World News (religion sections of major outlets) ──
    {
        "name": "BBC Religion",
        "url": "https://feeds.bbci.co.uk/news/religion/rss.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "NPR Religion",
        "url": "https://feeds.npr.org/1017/rss.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "Fox News Faith",
        "url": "https://moxie.foxnews.com/google-publisher/faith.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "The Guardian Religion",
        "url": "https://www.theguardian.com/world/religion/rss",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "Catholic News Agency",
        "url": "https://www.catholicnewsagency.com/rss/latest.rss",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "National Catholic Reporter",
        "url": "https://www.ncronline.org/rss.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "NYT Religion",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Religion.xml",
        "category": "news",
        "source_type": "world_news",
    },

    # ── Evangelical Author Substacks ──
    {
        "name": "Karen Swallow Prior",
        "url": "https://karenswallowprior.substack.com/feed",
        "category": "culture",
    },
    {
        "name": "Tish Harrison Warren",
        "url": "https://tishharrisonwarren.substack.com/feed",
        "category": "culture",
    },
    {
        "name": "Jake Meador (Mere Orthodoxy)",
        "url": "https://jakemeador.substack.com/feed",
        "category": "culture",
    },
    {
        "name": "Samuel James",
        "url": "https://samueljames.substack.com/feed",
        "category": "culture",
    },
    {
        "name": "Alan Jacobs",
        "url": "https://ayjay.substack.com/feed",
        "category": "culture",
    },
    {
        "name": "Kyle Worley",
        "url": "https://sacredslang.substack.com/feed",
        "category": "theology",
    },
    {
        "name": "Jen Wilkin",
        "url": "https://www.jenwilkin.net/blog?format=rss",
        "category": "theology",
    },
    {
        "name": "Carey Nieuwhof",
        "url": "https://careynieuwhof.com/feed/",
        "category": "church life",
    },
]
