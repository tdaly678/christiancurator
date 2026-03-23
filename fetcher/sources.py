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

    # ── World News (mainstream outlets — religion + general top news) ──
    {
        "name": "Associated Press",
        "url": "https://feeds.apnews.com/rss/apf-topnews",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "Associated Press Religion",
        "url": "https://feeds.apnews.com/rss/apf-Religion",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "BBC News",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "BBC Religion",
        "url": "https://feeds.bbci.co.uk/news/religion/rss.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "The New York Times",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "The New York Times Religion",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Religion.xml",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "Wall Street Journal",
        "url": "https://feeds.content.dowjones.io/public/rss/RSSWorldNews",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "The Guardian",
        "url": "https://www.theguardian.com/world/religion/rss",
        "category": "news",
        "source_type": "world_news",
    },
    {
        "name": "Washington Post",
        "url": "https://feeds.washingtonpost.com/rss/lifestyle/faith",
        "category": "news",
        "source_type": "world_news",
    },

    # ── Evangelical Author Substacks — Tier 2 ──
    {
        "name": "Jen Wilkin",
        "url": "https://www.jenwilkin.net/blog?format=rss",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Kyle Worley",
        "url": "https://sacredslang.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Phylicia Masonheimer",
        "url": "https://phyliciamasonheimer.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Laura Wifler",
        "url": "https://laurawifler.substack.com/feed",
        "category": "family",
        "independent": True,
    },

    # ── Evangelical Author Substacks — Tier 3 ──
    {
        "name": "Karen Swallow Prior",
        "url": "https://karenswallowprior.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Tish Harrison Warren",
        "url": "https://tishharrisonwarren.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Jake Meador (Mere Orthodoxy)",
        "url": "https://jakemeador.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Samuel James",
        "url": "https://samueljames.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Alan Jacobs",
        "url": "https://ayjay.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Carey Nieuwhof",
        "url": "https://careynieuwhof.com/feed/",
        "category": "church life",
        "independent": True,
    },

    # ── Independent Substacks — Tier 3 (from network discovery) ──
    # Major evangelical scholars and thinkers
    {
        "name": "Russell Moore",
        "url": "https://russellmoore.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Scot McKnight",
        "url": "https://scotmcknight.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Andy Crouch",
        "url": "https://andycrouch.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Carl Trueman",
        "url": "https://carltrueman.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Matthew Lee Anderson",
        "url": "https://matthewleeanderson.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "O. Alan Noble",
        "url": "https://oalannoble.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Ryan Burge",
        "url": "https://www.graphsaboutreligion.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Pew Research",
        "url": "https://www.pewresearch.org/religion/feed/",
        "category": "culture",
        "independent": False,
    },
    # Evangelical authors and voices
    {
        "name": "Sam Allberry",
        "url": "https://samallberry.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Trillia Newbell",
        "url": "https://trillianewbell.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Joy Clarkson",
        "url": "https://joyclarkson.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Mike Cosper",
        "url": "https://mikecosper.substack.com/feed",
        "category": "church life",
        "independent": True,
    },
    {
        "name": "Bethel McGrew",
        "url": "https://bethelmcgrew.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Bonnie Kristian",
        "url": "https://bonniekristian.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Aimee Byrd",
        "url": "https://aimeebyrd.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Nadya Williams",
        "url": "https://nadyawilliams.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Daniel K. Williams",
        "url": "https://danielkwilliams.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Tsh Oxenreider",
        "url": "https://tshoxenreider.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Gary Thomas",
        "url": "https://garythomas.substack.com/feed",
        "category": "devotional",
        "independent": True,
    },
    {
        "name": "Spencer Klavan",
        "url": "https://spencerklavan.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Diane Langberg",
        "url": "https://dianelangberg.substack.com/feed",
        "category": "church life",
        "independent": True,
    },
    {
        "name": "Timothy Paul Jones",
        "url": "https://timothypauljones.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "BibleProject",
        "url": "https://bibleproject.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Kate Shellnutt",
        "url": "https://kateshellnutt.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Jonathon Seidl",
        "url": "https://jonathonseidl.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
]
