"""
topic_classifier.py — Keyword-based topic classifier.

Maps each scored article to the 0-2 most relevant debate topic slugs
from the 36-topic taxonomy defined in frontend/topics_data.py.

No API calls. Runs as part of the daily pipeline after scoring.

Output added to each article:
  "debate_topics": list of matched topic slugs (0-2), ordered by match strength
"""

import os
import sys
import re

# Allow importing from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.topics_data import TOPICS


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation for keyword matching."""
    return re.sub(r"[^\w\s]", " ", text.lower())


def _strip_html_and_urls(text: str) -> str:
    """Remove URLs and HTML tags before keyword matching to avoid CDN/image URL false positives."""
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def _score_topic(text: str, keywords: list) -> int:
    """
    Return a match score: count of keyword hits in the text.
    Uses whole-word boundary matching so 'AI' doesn't hit 'faith'.
    """
    score = 0
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text):
            score += 1
    return score


def classify_article(article: dict) -> list:
    """
    Return up to 2 topic slugs that best match this article.
    Uses title + summary + topic_cluster for matching.
    Title matches are weighted 3x to prioritise specificity.

    Minimum score threshold of 2 required to avoid single-keyword noise
    (e.g. 'resurrection' alone matching 'heaven-hell', 'media' in CDN URLs
    matching 'technology', 'work' matching 'vocation', etc.).

    A score of 2 requires either:
      - at least 1 title keyword hit (title_hits*3 >= 3 > 2), OR
      - at least 2 body keyword hits
    """
    title_text = _normalize(article.get("title", ""))
    body_text  = _normalize(
        _strip_html_and_urls(article.get("summary", "")[:400])
        + " " + article.get("topic_cluster", "").replace("_", " ")
    )

    scores = []
    for topic in TOPICS:
        title_hits = _score_topic(title_text, topic["keywords"])
        body_hits  = _score_topic(body_text,  topic["keywords"])
        combined   = title_hits * 3 + body_hits
        if combined >= 2:
            scores.append((topic["slug"], combined))

    # Sort by score descending, return top 2 slugs
    scores.sort(key=lambda x: x[1], reverse=True)
    return [slug for slug, _ in scores[:2]]


def classify_articles(articles: list) -> list:
    """
    Run classify_article on every article in the list.
    Adds "debate_topics" field to each article (in-place).
    Returns the articles list.
    """
    for article in articles:
        article["debate_topics"] = classify_article(article)
    return articles


def compute_featured_topics(articles: list, top_n: int = 3) -> list:
    """
    Given a list of classified articles, return the top_n topics
    that have the most article matches, formatted as:
    [
      {
        "slug": "predestination",
        "name": "Predestination & Election",
        "hook": "...",
        "category": "Core Theology",
        "article_count": 4,
        "articles": [
          {"title": "...", "url": "...", "source_name": "...", "rewritten_title": "..."},
          ...
        ]
      },
      ...
    ]
    """
    from frontend.topics_data import TOPICS_BY_SLUG
    from collections import defaultdict

    topic_articles = defaultdict(list)

    for article in articles:
        for slug in article.get("debate_topics", []):
            topic_articles[slug].append({
                "title": article.get("title", ""),
                "rewritten_title": article.get("rewritten_title", ""),
                "url": article.get("url", ""),
                "source_name": article.get("source_name", ""),
                "author": article.get("author", ""),
                "published_display": _fmt_date(article.get("published", "")),
                "final_score": article.get("final_score", 0),
            })

    # Sort topics by article count, break ties by combined score
    ranked = []
    for slug, arts in topic_articles.items():
        if slug not in TOPICS_BY_SLUG:
            continue
        combined_score = sum(a["final_score"] for a in arts)
        ranked.append((slug, len(arts), combined_score, arts))

    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)

    featured = []
    for slug, count, _, arts in ranked[:top_n]:
        topic = TOPICS_BY_SLUG[slug]
        # Sort matched articles by score, take top 3
        arts_sorted = sorted(arts, key=lambda a: a["final_score"], reverse=True)[:3]
        featured.append({
            "slug": slug,
            "name": topic["name"],
            "hook": topic["hook"],
            "summary": topic.get("summary", topic["hook"]),
            "category": topic["category"],
            "article_count": count,
            "articles": arts_sorted,
        })

    return featured


def _fmt_date(published: str) -> str:
    """Parse an RFC 2822 published string and return a short display date like 'Apr 4'."""
    if not published:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(published)
        return dt.strftime("%b %-d")
    except Exception:
        return ""
