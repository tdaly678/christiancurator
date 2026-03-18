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

SCORING GUIDANCE:
- Score 1-10 based on theological depth, practical relevance to everyday Christian life, and writing quality.
- OBITUARIES and PERSON-SPECIFIC NEWS (deaths, appointments, awards, biographical profiles) should score 3 or below
  unless the person's story contains direct theological lessons or broad cultural significance beyond the individual.
  Example: "John Perkins Dies at 95" = score 3 max. "What John Perkins Taught Us About Reconciliation" = score normally.
- PODCAST EPISODE DESCRIPTIONS, RADIO RECAPS, and PROMOTIONAL ANNOUNCEMENTS should score 2 or below.
- LONG-FORM ESSAYS and THEOLOGICAL ARGUMENTS with clear practical application should score 7-10.

For each article, return a JSON object with:
  - "score": integer 1-10
  - "tags": array of 1-3 tags chosen ONLY from this exact list:
      theology, culture, apologetics, church life, missions, politics, devotional, news, family, prayer, suffering, work
  - "personas": array of 1-3 reader personas chosen ONLY from this exact list:
      pastor, professional, parent, student, women, seeker
  - "topic_cluster": a short snake_case string grouping articles on the same news story or topic
      (e.g. "john_perkins_death", "christian_nationalism_debate", "ai_and_faith", "iran_war_christians").
      Use the same cluster string for articles covering the same event or topic.
      Use "unique" if the article stands alone with no likely duplicates.
  - "perspective": one of "supportive", "critical", "neutral", "news"
      - "supportive": argues in favor of a position or person
      - "critical": argues against or raises concerns about a position or person
      - "neutral": balanced, informational, or devotional
      - "news": straight news reporting with no clear opinion

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
                article["topic_cluster"] = results[i].get("topic_cluster", "unique")
                article["perspective"] = results[i].get("perspective", "neutral")
            else:
                article["score"] = 5
                article["tags"] = []
                article["personas"] = []
                article["topic_cluster"] = "unique"
                article["perspective"] = "neutral"
    except Exception as e:
        print(f"  Batch scoring error: {e}")
        for article in articles:
            article["score"] = 5
            article["tags"] = []
            article["personas"] = []
            article["topic_cluster"] = "unique"
            article["perspective"] = "neutral"
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


# Source tier multipliers — applied to base score before recency boost
SOURCE_TIER_MULTIPLIERS = {
    # Tier 1A — 1.3x
    "The Gospel Coalition":    1.3,
    "Desiring God":            1.3,
    "Ligonier Ministries":     1.3,
    "9Marks":                  1.3,
    # Tier 1 — 1.2x
    "Christianity Today":      1.2,
    "First Things":            1.2,
    "Crossway":                1.2,
    "Mere Orthodoxy":          1.2,
    "American Reformer":       1.2,
    # Tier 2 — 1.05x
    "World Magazine":          1.05,
    "Relevant Magazine":       1.05,
    "Reformation21":           1.05,
    "Jen Wilkin":              1.05,
    "Kyle Worley":             1.05,
    # Tier 3 — 1.0x (default, all others)
    # Tier 4 — 0.85x
    "BBC Religion":            0.85,
    "The New York Times":      0.85,
    "The Guardian":            0.85,
    "Associated Press":        0.85,
    "Washington Post":         0.85,
}
DEFAULT_TIER_MULTIPLIER = 1.0  # Tier 3 author substacks and unlisted sources

PREVIOUSLY_SHOWN_PENALTY = 4.0   # applied to articles already surfaced on the site
DUPLICATE_TOPIC_PENALTY   = 3.0   # applied to same-topic same-perspective duplicates
OPPOSING_VIEWS_BOOST      = 1.0   # applied to articles that form an opposing pair


def apply_topic_deduplication(articles: list[dict]) -> list[dict]:
    """
    For articles sharing the same topic_cluster:
    - If they have opposing perspectives (one supportive + one critical), boost both.
    - If they share the same perspective, penalize all but the highest scorer.
    Operates on final_score in-place.
    """
    from collections import defaultdict
    clusters = defaultdict(list)
    for article in articles:
        cluster = article.get("topic_cluster", "unique")
        if cluster and cluster != "unique":
            clusters[cluster].append(article)

    for cluster, group in clusters.items():
        if len(group) < 2:
            continue
        perspectives = {a.get("perspective", "neutral") for a in group}
        has_opposing = "supportive" in perspectives and "critical" in perspectives

        if has_opposing:
            # Boost the best supportive and best critical article
            supportive = sorted([a for a in group if a.get("perspective") == "supportive"],
                                key=lambda x: x["final_score"], reverse=True)
            critical = sorted([a for a in group if a.get("perspective") == "critical"],
                              key=lambda x: x["final_score"], reverse=True)
            if supportive:
                supportive[0]["final_score"] = round(
                    min(supportive[0]["final_score"] + OPPOSING_VIEWS_BOOST, 10.0), 2)
                supportive[0]["opposing_pair"] = True
            if critical:
                critical[0]["final_score"] = round(
                    min(critical[0]["final_score"] + OPPOSING_VIEWS_BOOST, 10.0), 2)
                critical[0]["opposing_pair"] = True
            # Penalize the rest in the cluster
            boosted_urls = set()
            if supportive: boosted_urls.add(supportive[0]["url"])
            if critical: boosted_urls.add(critical[0]["url"])
            for a in group:
                if a["url"] not in boosted_urls:
                    a["final_score"] = round(max(a["final_score"] - DUPLICATE_TOPIC_PENALTY, 0.0), 2)
                    a["duplicate_suppressed"] = True
        else:
            # Same topic, same take — keep only the best, penalize the rest
            best = max(group, key=lambda x: x["final_score"])
            for a in group:
                if a["url"] != best["url"]:
                    a["final_score"] = round(max(a["final_score"] - DUPLICATE_TOPIC_PENALTY, 0.0), 2)
                    a["duplicate_suppressed"] = True

    suppressed = sum(1 for a in articles if a.get("duplicate_suppressed"))
    if suppressed:
        print(f"  Topic deduplication: suppressed {suppressed} duplicate-topic articles.")
    return articles


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

    # Step 2: Apply source tier multiplier + recency boost → store in final_score
    shown_urls = shown_urls or set()
    previously_shown_count = 0
    for article in scored:
        base = float(article.get("score") or 5)
        multiplier = SOURCE_TIER_MULTIPLIERS.get(article.get("source_name", ""), DEFAULT_TIER_MULTIPLIER)
        base = round(min(base * multiplier, 10.0), 2)
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

    # Step 4: Apply topic deduplication (suppress same-topic same-perspective duplicates,
    #          boost opposing viewpoint pairs)
    scored = apply_topic_deduplication(scored)

    # Step 5: Apply source diversity penalty and hard cap
    scored = apply_diversity_penalty(scored)

    # Step 6: Final sort
    return sorted(scored, key=lambda a: a["final_score"], reverse=True)
