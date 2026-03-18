"""
scorer.py — uses Claude to score and tag articles in batches for efficiency.

Each article receives:
  - score:       int 1-10 from Claude (content quality & relevance)
  - final_score: float after recency boost and diversity penalty
  - tags:        list of topic strings
  - personas:    list of reader persona strings
"""

import os
import json
import anthropic
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

BATCH_SIZE = 10  # articles per API call

# Recency boost: articles published within N hours get a bonus
RECENCY_BOOSTS = [
    (24,  1.5),   # published within 24h  → +1.5
    (48,  0.75),  # published within 48h  → +0.75
    (72,  0.25),  # published within 72h  → +0.25
]

# Diversity: each additional article from the same source is penalised
DIVERSITY_PENALTY_PER_EXTRA = 0.75  # -0.75 per article beyond the first
MAX_PER_SOURCE = 5                  # hard cap per source

WORLD_NEWS_FILTER_PROMPT = """\
You are a filter for an evangelical Christian news digest. Review each article below and decide if it is relevant to an evangelical Protestant audience.

An article IS relevant if it covers: Protestant or Catholic Christianity, religious freedom, church-state issues, persecution of Christians, Christian cultural influence, Christian leaders or institutions, faith and public life, or major religious events affecting Christians.

An article is NOT relevant if it primarily covers: Islam, Hinduism, Buddhism, Judaism (unless related to Christian-Jewish relations), general spirituality, New Age, atheism, or topics with no direct Christian angle.

For each article, return a JSON object with:
  - "relevant": true or false

Respond with ONLY a JSON array, one object per article, in the same order.

Articles:
{articles}
"""

BATCH_PROMPT = """\
You are a curator for a Christian news digest. Score and tag each article below.

For each article, return a JSON object with:
  - "score": integer 1-10 (how relevant and valuable this is for a Christian audience)
  - "tags": array of 1-3 tags chosen ONLY from this exact list:
      theology, culture, apologetics, church life, missions, politics, devotional, news, family, prayer, suffering, work
  - "personas": array of 1-3 reader personas who would find this most relevant, chosen ONLY from this exact list:
      pastor, professional, parent, student, women, seeker

You MUST only use tags and personas from those exact lists. Do not invent new values.

Respond with ONLY a JSON array containing one object per article, in the same order.
No explanation, no markdown, just the raw JSON array.

Articles:
{articles}
"""


def filter_world_news_batch(articles: list[dict]) -> list[dict]:
    """Filter world news articles for evangelical relevance. Returns only relevant articles."""
    articles_text = "\n".join(
        f"{i+1}. Title: {a['title']}\n   Summary: {a['summary'][:200]}"
        for i, a in enumerate(articles)
    )
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": WORLD_NEWS_FILTER_PROMPT.format(articles=articles_text)}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        results = json.loads(raw)
        return [a for i, a in enumerate(articles) if i < len(results) and results[i].get("relevant", False)]
    except Exception as e:
        print(f"  World news filter error: {e}")
        return articles  # on error, keep all and let scoring sort it out


def score_batch(articles: list[dict]) -> list[dict]:
    """Score and tag a batch of articles in a single API call."""
    articles_text = "\n".join(
        f"{i+1}. Title: {a['title']}\n   Summary: {a['summary'][:200]}"
        for i, a in enumerate(articles)
    )
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": BATCH_PROMPT.format(articles=articles_text)}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if not raw:
            print(f"  Warning: empty response from API. Stop reason: {message.stop_reason}")
            raise ValueError("Empty response")
        results = json.loads(raw)
        for i, article in enumerate(articles):
            if i < len(results):
                article["score"] = results[i].get("score", 5)
                article["tags"] = results[i].get("tags", [])
                article["personas"] = results[i].get("personas", [])
            else:
                article["score"] = 5
                article["tags"] = []
                article["personas"] = []
    except Exception as e:
        print(f"  Batch scoring error: {e}")
        for article in articles:
            article["score"] = 5
            article["tags"] = []
            article["personas"] = []
    return articles


def apply_recency_boost(article: dict) -> float:
    """Return a recency bonus based on how recently the article was published."""
    published = article.get("published", "")
    if not published:
        return 0.0
    try:
        pub_dt = parsedate_to_datetime(published)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        hours_old = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
        for max_hours, boost in RECENCY_BOOSTS:
            if hours_old <= max_hours:
                return boost
    except Exception:
        pass
    return 0.0


def apply_diversity_penalty(articles: list[dict]) -> list[dict]:
    """
    Apply a progressive score penalty for sources that appear multiple times,
    and enforce a hard cap of MAX_PER_SOURCE articles per source.
    Operates on final_score in-place.
    """
    source_counts = defaultdict(int)
    kept = []
    for article in articles:
        source = article["source_name"]
        source_counts[source] += 1
        count = source_counts[source]
        if count > MAX_PER_SOURCE:
            continue  # hard cap — drop article entirely
        penalty = (count - 1) * DIVERSITY_PENALTY_PER_EXTRA
        article["final_score"] = round(article["final_score"] - penalty, 2)
        kept.append(article)
    return kept


PREVIOUSLY_SHOWN_PENALTY = 4.0  # applied to articles already surfaced on the site


def score_articles(articles: list[dict], shown_urls: set = None) -> list[dict]:
    """Score, boost, and diversify all articles. Returns sorted by final_score."""
    # Step 0: Filter world news articles for evangelical relevance
    world_news = [a for a in articles if a.get("source_type") == "world_news"]
    christian = [a for a in articles if a.get("source_type") != "world_news"]
    if world_news:
        print(f"  Filtering {len(world_news)} world news articles for evangelical relevance...")
        kept = []
        for i in range(0, len(world_news), BATCH_SIZE):
            kept.extend(filter_world_news_batch(world_news[i:i + BATCH_SIZE]))
        print(f"  Kept {len(kept)} of {len(world_news)} world news articles after relevance filter")
        articles = christian + kept

    # Step 1: Claude scoring in batches
    scored = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        print(f"  Scoring articles {i+1}-{min(i+BATCH_SIZE, len(articles))}...")
        scored.extend(score_batch(batch))

    # Step 2: Apply recency boost → store in final_score
    shown_urls = shown_urls or set()
    previously_shown_count = 0
    for article in scored:
        base = float(article.get("score") or 5)
        boost = apply_recency_boost(article)
        raw_final = round(min(base + boost, 10.0), 2)

        # Apply previously-shown penalty
        if article.get("url") in shown_urls:
            raw_final = round(max(raw_final - PREVIOUSLY_SHOWN_PENALTY, 0.0), 2)
            article["previously_shown"] = True
            previously_shown_count += 1

        article["final_score"] = raw_final
        if boost > 0:
            article["recency_boost"] = boost

    if previously_shown_count:
        print(f"  Applied previously-shown penalty to {previously_shown_count} articles.")

    # Step 3: Sort by final_score before diversity pass
    scored.sort(key=lambda a: a["final_score"], reverse=True)

    # Step 4: Apply source diversity penalty and hard cap
    scored = apply_diversity_penalty(scored)

    # Step 5: Final sort
    return sorted(scored, key=lambda a: a["final_score"], reverse=True)
