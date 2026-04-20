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

    # ── Tier 1A: Institutional Evangelical Voices ──
    {
        "name": "EFCA Blog",
        "url": "https://blogs.efca.org/feed/",
        "category": "theology",
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
        "name": "Daily Dose of Greek",
        "url": "https://dailydoseofgreek.com/feed/",
        "category": "theology",
        "independent": True,
    },
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
        # Canonical home per author's own site (Challies 2026 roundup)
        "url": "https://www.digitalliturgies.net/feed",
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
        # Canonical feed per author's site (Challies 2026 roundup)
        "url": "https://newsletter.oalannoble.com/feed",
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
    {
        "name": "Barna Group",
        "url": "https://www.barna.com/feed/",
        "category": "culture",
        "independent": False,
    },
    {
        "name": "Lifeway Research",
        "url": "https://lifewayresearch.com/feed/",
        "category": "culture",
        "independent": False,
    },
    {
        "name": "Ed Stetzer",
        "url": "https://edstetzer.substack.com/feed",
        "category": "culture",
        "independent": True,
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
        # Canonical feed "Further Up" per author's own site (Challies 2026)
        "url": "https://www.furtherup.net/feed",
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

    # ── New Additions: Institutional Ministries ──
    {
        "name": "Albert Mohler",
        "url": "https://albertmohler.com/feed",
        "category": "culture",
    },
    {
        "name": "Gospel in Life",
        "url": "https://gospelinlife.com/feed/",
        "category": "theology",
    },
    {
        "name": "The Aquila Report",
        "url": "https://theaquilareport.com/feed/",
        "category": "theology",
    },

    # ── New Additions: Black Evangelical Voices ──
    {
        "name": "Jemar Tisby",
        "url": "https://jemartisby.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Faithfully Magazine",
        "url": "https://faithfullymagazine.com/feed/",
        "category": "culture",
    },

    # ── New Additions: Apologetics ──
    {
        "name": "Sean McDowell",
        "url": "https://seanmcdowell.org/feed/",
        "category": "theology",
        "independent": True,
    },

    # ── New Additions: Reformed Voices ──
    {
        "name": "Kevin DeYoung",
        "url": "https://www.thegospelcoalition.org/blogs/kevin-deyoung/feed/",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Gavin Ortlund",
        "url": "https://truthunites.org/feed/",
        "category": "theology",
        "independent": True,
    },

    # ── New Additions: Young Evangelical Voices ──
    {
        "name": "Patrick Miller",
        "url": "https://patrickkmiller.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Hannah Anderson",
        "url": "https://sometimesalight.substack.com/feed",
        "category": "theology",
        "independent": True,
    },

    # ── April 2026: Tier A Independent Expansion ──
    # Anchored in Tim Challies' 30 Christian Substacks (Feb 2026) + wider scan
    # of prominent evangelical scholars, pastors, and journalists publishing
    # independently. All marked independent: True so they feed the floor
    # guarantee + publishing-frequency boost in scorer.py.

    # Cultural commentary & public theology
    {
        "name": "Aaron Renn",
        # "Life in the Negative World" author; posts several times a week
        "url": "https://www.aaronrenn.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Stephen McAlpine",
        # Australian public theologian ("Being the Bad Guys")
        "url": "https://stephenmcalpine.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Chris Martin",
        # Moody Publishers creative director; tech & digital discipleship
        "url": "https://www.chrismartin.fyi/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Daniel Darling",
        # Director, Southwestern Baptist Land Center for Cultural Engagement
        "url": "https://dandarling.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
    {
        "name": "Katelyn Beaty",
        # Former CT managing editor; author of "Celebrities for Jesus"
        "url": "https://katelynbeaty.substack.com/feed",
        "category": "culture",
        "independent": True,
    },

    # Longest-running evangelical blogger
    {
        "name": "Tim Challies",
        # 22+ years of daily Christian blogging — canonical hub
        "url": "https://www.challies.com/feed/",
        "category": "theology",
        "independent": True,
    },

    # Pastors & pastoral theology
    {
        "name": "Wyatt Graham",
        # Canadian pastor-theologian; engages primary sources
        "url": "https://www.wyattgraham.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Tom Sugimura",
        # Pastor & biblical counselor ("Counsel the Word")
        "url": "https://tomsugi.substack.com/feed",
        "category": "church life",
        "independent": True,
    },
    {
        "name": "J.A. Medders",
        # Pastor-author; "Spiritual Theology" (Spurgeon-adjacent)
        "url": "https://www.spiritualtheology.net/feed",
        "category": "theology",
        "independent": True,
    },

    # Biblical scholarship
    {
        "name": "Mitchell Chase",
        # SBTS biblical theology prof ("Biblical Theology")
        "url": "https://mitchchase.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Michael Bird",
        # Australian NT scholar ("Word from the Bird")
        "url": "https://michaelfbird.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Nijay Gupta",
        # Northern Seminary NT scholar
        "url": "https://nijaykgupta.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Carmen Joy Imes",
        # Biola OT scholar ("Being God's Image")
        "url": "https://carmenjoyimes.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Beth Felker Jones",
        # Theologian; "Church Blogmatics"
        "url": "https://bethfelkerjones.substack.com/feed",
        "category": "theology",
        "independent": True,
    },

    # Historians
    {
        "name": "Thomas Kidd",
        # Midwestern Baptist Theological Seminary church historian
        "url": "https://thomaskidd.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Chris Gehrz",
        # "The Pietist Schoolman"; Bethel University historian
        "url": "https://chrisgehrz.substack.com/feed",
        "category": "culture",
        "independent": True,
    },

    # Devotional / formation / creative
    {
        "name": "Emily P. Freeman",
        # NYT bestselling author; discernment & vocation
        "url": "https://emilypfreeman.substack.com/feed",
        "category": "devotional",
        "independent": True,
    },
    {
        "name": "A.J. Swoboda",
        # Theologian, Bushnell University; consistent weekly publishing
        "url": "https://ajswoboda.substack.com/feed",
        "category": "theology",
        "independent": True,
    },
    {
        "name": "Nicholas McDonald",
        # "The Bard Owl" — deconstruction-survivor voice, arts & faith
        "url": "https://thebardowl.substack.com/feed",
        "category": "culture",
        "independent": True,
    },
]
