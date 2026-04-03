"""
topic_matcher.py — matches today's articles and daily themes to relevant
deep-dive topic pages, so the pipeline can automatically surface "Going
deeper" links in the digest and daily pulse pages.

Usage:
    from frontend.topic_matcher import match_topics
    topics = match_topics(articles, daily_summary)
    # Returns: [{"slug": "atonement", "label": "The Atonement"}, ...]
"""

from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Topic definitions: each entry maps a slug to its display label and the
# keywords that signal this topic is covered in today's content.
# Keywords are matched case-insensitively against article titles and themes.
# ---------------------------------------------------------------------------
TOPICS: list[dict] = [
    {
        "slug": "atonement",
        "label": "The Atonement",
        "keywords": [
            "atonement", "penal substitut", "christus victor", "cross of christ",
            "crucifixion", "blood of christ", "ransom", "propitiation", "expiation",
            "sacrifice of jesus", "wrath of god", "substitution",
        ],
    },
    {
        "slug": "justification-by-faith",
        "label": "Justification by Faith",
        "keywords": [
            "justification", "justified by faith", "imputation", "imputed righteousness",
            "sola fide", "faith alone", "righteousness of christ", "forensic",
            "declared righteous", "new perspective on paul",
        ],
    },
    {
        "slug": "biblical-inerrancy",
        "label": "Biblical Inerrancy",
        "keywords": [
            "inerrancy", "inerrant", "infallibility", "infallible", "scripture authority",
            "authority of scripture", "biblical authority", "chicago statement",
            "biblical reliability", "errancy",
        ],
    },
    {
        "slug": "sanctification",
        "label": "Sanctification",
        "keywords": [
            "sanctification", "sanctified", "holiness", "holy living", "progressive sanctification",
            "definitive sanctification", "mortification", "mortify", "growth in grace",
            "spiritual growth", "keswick",
        ],
    },
    {
        "slug": "heaven-hell-eternity",
        "label": "Heaven, Hell & Eternity",
        "keywords": [
            "heaven", "hell", "eternity", "eternal life", "annihilationism", "annihilation",
            "universalism", "new creation", "new earth", "resurrection body",
            "eschatology", "eternal punishment", "afterlife", "judgment day",
        ],
    },
    {
        "slug": "suffering-and-providence",
        "label": "Suffering & Providence",
        "keywords": [
            "suffering", "providence", "theodicy", "problem of evil", "lament",
            "grief", "loss", "pain", "sovereignty of god", "why does god allow",
            "hardship", "trial", "affliction",
        ],
    },
    {
        "slug": "prayer",
        "label": "Prayer",
        "keywords": [
            "prayer", "praying", "intercession", "intercede", "contemplative prayer",
            "corporate prayer", "fasting and prayer", "quiet time", "devotional",
        ],
    },
    {
        "slug": "gender-and-biblical-anthropology",
        "label": "Gender & Biblical Anthropology",
        "keywords": [
            "gender", "transgender", "gender dysphoria", "sexuality", "same-sex",
            "homosexuality", "biblical anthropology", "image of god", "imago dei",
            "male and female", "sexual identity", "lgbtq", "same sex attraction",
        ],
    },
    {
        "slug": "creation-evolution",
        "label": "Creation & Evolution",
        "keywords": [
            "creation", "evolution", "creationism", "young earth", "old earth",
            "intelligent design", "genesis 1", "genesis 2", "evolutionary creationism",
            "theistic evolution", "six days", "age of the earth", "darwin",
        ],
    },
    {
        "slug": "local-church",
        "label": "The Local Church",
        "keywords": [
            "local church", "ecclesiology", "church membership", "dechurching",
            "church decline", "marks of the church", "gathered church",
            "church community", "congregation", "church health",
        ],
    },
    {
        "slug": "membership",
        "label": "Church Membership",
        "keywords": [
            "church membership", "church member", "9marks", "church discipline",
            "church roll", "joining a church", "covenant membership",
        ],
    },
    {
        "slug": "church-planting",
        "label": "Church Planting & Revitalization",
        "keywords": [
            "church planting", "church plant", "church revitalization", "replanting",
            "new church", "starting a church", "church multiplication",
        ],
    },
    {
        "slug": "complementarianism-egalitarianism",
        "label": "Complementarianism & Egalitarianism",
        "keywords": [
            "complementarian", "egalitarian", "women in ministry", "female pastor",
            "women pastors", "women preachers", "male headship", "gender roles",
            "women elders", "ordination of women",
        ],
    },
    {
        "slug": "discipleship",
        "label": "Discipleship",
        "keywords": [
            "discipleship", "disciple-making", "making disciples", "formation",
            "spiritual formation", "mentoring", "one-on-one", "follow jesus",
            "christian formation", "discipling",
        ],
    },
    {
        "slug": "preaching",
        "label": "Preaching",
        "keywords": [
            "preaching", "sermon", "expository", "expository preaching", "homiletics",
            "biblical preaching", "pulpit", "proclaiming the word", "preach",
        ],
    },
    {
        "slug": "spiritual-disciplines",
        "label": "Spiritual Disciplines",
        "keywords": [
            "spiritual disciplines", "fasting", "sabbath", "solitude", "silence",
            "scripture reading", "bible reading", "spiritual practice", "rule of life",
            "dallas willard", "richard foster",
        ],
    },
    {
        "slug": "marriage-and-family",
        "label": "Marriage & Family",
        "keywords": [
            "marriage", "family", "husband and wife", "covenant marriage",
            "divorce", "remarriage", "christian home", "ephesians 5",
        ],
    },
    {
        "slug": "christian-parenting",
        "label": "Christian Parenting",
        "keywords": [
            "parenting", "christian parenting", "raising children", "children",
            "faith of children", "family worship", "prodigal", "parent",
        ],
    },
    {
        "slug": "vocation-and-work",
        "label": "Vocation & Work",
        "keywords": [
            "vocation", "calling", "work", "labor", "marketplace", "faith and work",
            "monday morning", "theology of work", "workplace",
        ],
    },
    {
        "slug": "mental-health",
        "label": "Mental Health & Faith",
        "keywords": [
            "mental health", "depression", "anxiety", "counseling", "therapy",
            "psychology", "mental illness", "emotional health", "trauma",
            "suicide", "burnout", "pastor burnout",
        ],
    },
    {
        "slug": "technology",
        "label": "Technology",
        "keywords": [
            "artificial intelligence", "ai", "technology", "smartphone",
            "digital", "social media", "algorithm", "silicon valley",
            "tech", "screen time",
        ],
    },
    {
        "slug": "technology-and-discipleship",
        "label": "Technology & Discipleship",
        "keywords": [
            "technology and discipleship", "digital discipleship", "phone addiction",
            "social media discipleship", "distraction", "attention", "formation and tech",
            "online church",
        ],
    },
    {
        "slug": "politics-and-the-church",
        "label": "Politics & the Church",
        "keywords": [
            "christian nationalism", "politics", "political", "voting", "election",
            "government", "two kingdoms", "church and state", "public square",
            "civic engagement", "republican", "democrat", "trump", "policy",
        ],
    },
    {
        "slug": "missions-and-evangelism",
        "label": "Missions & Evangelism",
        "keywords": [
            "missions", "missionary", "evangelism", "evangelistic", "great commission",
            "unreached", "gospel proclamation", "church growth", "outreach",
            "william carey", "reaching the lost",
        ],
    },
    {
        "slug": "apologetics",
        "label": "Apologetics",
        "keywords": [
            "apologetics", "apologist", "defend the faith", "atheism", "atheist",
            "skepticism", "reason and faith", "evidence for god", "cosmological",
            "teleological", "resurrection evidence", "historical jesus",
        ],
    },
    {
        "slug": "racial-reconciliation",
        "label": "Racial Reconciliation",
        "keywords": [
            "racial reconciliation", "race", "racism", "racial justice",
            "multiethnic church", "diversity", "black church", "jim crow",
            "civil rights", "reparations", "critical race theory", "crt",
        ],
    },
]

MAX_TOPICS = 3  # max number of "Going deeper" topics to surface per day


def _normalise(text: str) -> str:
    """Lowercase and collapse whitespace for consistent matching."""
    return re.sub(r"\s+", " ", text.lower().strip())


def match_topics(articles: list[dict], daily_summary: dict | None) -> list[dict]:
    """
    Scan article titles and daily themes to find relevant topic pages.

    Parameters
    ----------
    articles : list of article dicts (must have a 'title' key)
    daily_summary : the daily_summary dict (may have a 'themes' key and
                    'paragraphs_plain' list)

    Returns
    -------
    List of dicts [{slug, label}, ...] — up to MAX_TOPICS, in match-score order.
    """
    # Build the corpus of text to search
    corpus_parts: list[str] = []

    for a in articles:
        if a.get("title"):
            corpus_parts.append(a["title"])

    if daily_summary:
        for theme in daily_summary.get("themes") or []:
            corpus_parts.append(theme)
        for para in daily_summary.get("paragraphs_plain") or []:
            corpus_parts.append(para[:400])  # first 400 chars of each paragraph

    corpus = _normalise(" ".join(corpus_parts))

    # Score each topic by how many of its keywords appear in the corpus
    scored: list[tuple[int, dict]] = []
    for topic in TOPICS:
        hits = sum(1 for kw in topic["keywords"] if kw in corpus)
        if hits > 0:
            scored.append((hits, topic))

    # Sort descending by hit count; take up to MAX_TOPICS
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:MAX_TOPICS]]
