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
import time
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

# Recency penalty: articles older than N days get penalised
# Articles older than HARD_CUTOFF_DAYS are dropped entirely in score_articles()
RECENCY_PENALTIES = [
    (7,   -2.0),  # 3–7 days old   → -2.0
    (14,  -4.0),  # 7–14 days old  → -4.0
    (30,  -6.0),  # 14–30 days old → -6.0
]
HARD_CUTOFF_DAYS = 30  # articles older than this are excluded entirely

# Diversity: each additional article from the same source is penalised
DIVERSITY_PENALTY_PER_EXTRA = 0.75  # -0.75 per article beyond the first
MAX_PER_SOURCE = 5                  # hard cap per source

WORLD_NEWS_FILTER_PROMPT = """\
You are a filter for a Christian news digest that also surfaces the most important world event each day.

For each article, return a JSON object with:
  - "relevant": true or false
      An article IS relevant if it covers: Protestant or Catholic Christianity, religious freedom,
      church-state issues, persecution of Christians, Christian cultural influence, Christian leaders
      or institutions, faith and public life, or major religious events affecting Christians.
      An article is NOT relevant if it primarily covers: Islam, Hinduism, Buddhism, Judaism (unless
      related to Christian-Jewish relations), general spirituality, New Age, or topics with no
      direct Christian angle.
  - "top_story": true for exactly ONE article — the single most important and newsworthy world event
      of the day based on significance, global impact, and timeliness. This article should be surfaced
      regardless of whether it has a direct Christian angle. Choose the story that a well-informed
      person would consider the most consequential news of the day. All other articles should have
      "top_story": false.

Respond with ONLY a JSON array, one object per article, in the same order.

Articles:
{articles}
"""

BATCH_PROMPT = """\
You are a curator for a Christian news digest targeting EVANGELICAL PROTESTANT Christians.

SCORING GUIDANCE:
- Score 1-10 based on theological depth, practical relevance to everyday Christian life, and writing quality.

- SCORE 8-10: Essays or devotionals that (a) explicitly connect the topic to the gospel — Christ's death,
  resurrection, or atonement as the answer, not just general theism — (b) exposit a specific Scripture passage
  with context and meaning rather than merely citing verses as footnotes, and (c) close with concrete application
  for the Christian life. Bonus: articles that begin by naming a real struggle or question the reader faces, then
  address it biblically. Length alone does not earn a high score — a short devotional that does all three deserves
  8 more than a long essay that does none.

- SCORE 6-7: Solid theological or practical articles that apply Scripture to Christian life but lack an explicit
  gospel connection, OR good cultural commentary that offers a biblically-grounded constructive alternative (not
  just critique). Interviews and roundtables with substantive theological content may fall here.

- SCORE 5-6: CULTURAL COMMENTARY that critiques secular trends or cultural moments without offering a substantive
  biblical or gospel-based constructive response — the observation without the answer. Also score 5-6: listicles
  and pragmatic "how-to" articles that assume Christian motivation without grounding it doctrinally.

- SCORE 4-5: DATA, RESEARCH, or STATISTICS-DRIVEN articles about Christian trends, church demographics,
  religious identity, or sociological observations about faith in America. These are genuinely valuable for
  context but are not devotionally formative. Tag these with "data" — they are curated separately in a
  Research & Data section and should NOT compete with theological or devotional content for main feed placement.
  Examples: church attendance surveys, generational faith trends, religious polling data, Pew/Barna/Burge analysis.

- OBITUARIES, TRIBUTES, and PERSON-SPECIFIC NEWS (deaths, memorial essays, tribute pieces, appointments, awards,
  biographical profiles) should score 4 or below. This includes legacy/tribute framing such as "A Courageous Voice
  for...", "Remembering...", "Celebrating the Life of...", or "[Name]: [Adjective] [Noun]" title patterns.
  Only score 5+ if the article contains substantial theological teaching that stands fully independent of the
  person — i.e., a reader would benefit equally without knowing who the subject is.
  Example: "John Perkins Dies at 95" = score 2 max. "John Perkins: A Courageous Voice for Justice" = score 4 max.
  "What Racial Reconciliation Demands of the Church Today" (Perkins as one example among many) = score normally.

- PODCAST EPISODE DESCRIPTIONS, RADIO RECAPS, and PROMOTIONAL ANNOUNCEMENTS should score 2 or below.

- CATHOLIC-SPECIFIC CONTENT should score 3 or below. This includes: papal encyclicals, papal appointments,
  Vatican decisions, the Synod on Synodality, Catholic doctrine debates, Pope Francis statements, Cardinal
  appointments, and other Roman Catholic institutional news. The audience is evangelical Protestant — they
  have limited interest in internal Catholic Church affairs. Exception: score normally if the article has
  clear relevance to all Christians (e.g., broad pro-life coalitions, shared persecution, ecumenical topics
  with direct evangelical application).

For each article, return a JSON object with:
  - "score": integer 1-10
  - "tags": array of 1-3 tags chosen ONLY from this exact list:
      theology, culture, apologetics, church life, missions, politics, devotional, news, family, prayer, suffering, work, data
      Use "data" for research, statistics, polling, and sociological analysis articles (Pew Research, Barna Group, Ryan Burge,
      Lifeway Research, Ed Stetzer, PRRI, Gallup, etc.)
  - "personas": array of 1-3 reader personas chosen ONLY from this exact list:
      pastor, professional, parent, student, women, seeker
  - "topic_cluster": a short snake_case string grouping articles on the same news story or topic.
      IMPORTANT: Articles about the same person or institution should share a cluster even if the angle differs.
      Examples: all Pope Francis / Vatican / synodality articles → "pope_francis_vatican";
      "john_perkins_death", "christian_nationalism_debate", "ai_and_faith", "iran_war_christians".
      Use the same cluster string for articles covering the same event, person, or topic.
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


MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]  # seconds between retries


def _api_call_with_retry(fn, label="API call"):
    """Call fn() with exponential backoff on 529 overload errors."""
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            return fn()
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt <= MAX_RETRIES:
                print(f"  {label}: API overloaded (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise
    return None  # should not reach here


def filter_world_news_batch(articles: list[dict]) -> list[dict]:
    """Filter world news articles for evangelical relevance and flag the top world story."""
    articles_text = "\n".join(
        f"{i+1}. Title: {a['title']}\n   Summary: {a['summary'][:200]}"
        for i, a in enumerate(articles)
    )
    try:
        def _call():
            return client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": WORLD_NEWS_FILTER_PROMPT.format(articles=articles_text)}],
            )
        message = _api_call_with_retry(_call, "World news filter")
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        results = json.loads(raw)
        kept = []
        for i, a in enumerate(articles):
            if i >= len(results):
                break
            if results[i].get("top_story", False):
                a["top_world_story"] = True
                kept.append(a)
            elif results[i].get("relevant", False):
                kept.append(a)
        return kept
    except Exception as e:
        print(f"  World news filter error: {e}")
        return articles


def score_batch(articles: list[dict]) -> list[dict]:
    """Score and tag a batch of articles in a single API call."""
    # Tier 1A sources get a longer summary window so the scorer sees enough
    # theological content to distinguish an 8 from a 6.
    def _summary_limit(article: dict) -> int:
        return 400 if article.get("source_name", "") in TIER_1A_SOURCES else 200

    articles_text = "\n".join(
        f"{i+1}. Title: {a['title']}\n   Summary: {a['summary'][:_summary_limit(a)]}"
        for i, a in enumerate(articles)
    )
    try:
        def _call():
            return client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": BATCH_PROMPT.format(articles=articles_text)}],
            )
        message = _api_call_with_retry(_call, "Scoring")
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
    """Return a recency bonus (positive) or penalty (negative) based on article age.

    - Within 24h:   +1.5
    - Within 48h:   +0.75
    - Within 72h:   +0.25
    - 3–7 days:     -2.0
    - 7–14 days:    -4.0
    - 14–30 days:   -6.0
    - 30+ days:     article is excluded entirely by score_articles()
    """
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
        # No boost matched — check penalty tiers (in days)
        days_old = hours_old / 24
        for max_days, penalty in RECENCY_PENALTIES:
            if days_old <= max_days:
                return penalty
        # Older than all penalty tiers — will be hard-dropped in score_articles()
        return -99.0
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
        cap = source_max(source)
        if count > cap:
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
    "Phylicia Masonheimer":    1.05,
    "Laura Wifler":            1.05,
    # Tier 3 — 1.0x (default, all others)
    # Tier 4A — 0.90x (high-quality centrist outlets)
    "Associated Press":          0.90,
    "Associated Press Religion": 0.90,
    "BBC News":                  0.90,
    "BBC Religion":              0.90,
    "The New York Times":        0.90,
    "The New York Times Religion": 0.90,
    "Wall Street Journal":       0.90,
    # Tier 4B — 0.80x (perspective-driven outlets)
    "The Guardian":              0.80,
    "Washington Post":           0.80,
}
DEFAULT_TIER_MULTIPLIER = 1.0  # Tier 3 author substacks and unlisted sources

# Per-tier hard caps on articles per source per day
TIER_1A_SOURCES = {"The Gospel Coalition", "Desiring God", "Ligonier Ministries", "9Marks"}
TIER_1_SOURCES  = {"Christianity Today", "First Things", "Crossway", "Mere Orthodoxy", "American Reformer"}
TIER_2_SOURCES  = {"World Magazine", "Relevant Magazine", "Reformation21", "Jen Wilkin", "Kyle Worley",
                   "Phylicia Masonheimer", "Laura Wifler"}

# Independent author sources (Substacks + personal blogs) — used for the
# independent floor guarantee (at least MIN_INDEPENDENT articles per day)
INDEPENDENT_SOURCES = {
    # Tier 2 independents
    "Jen Wilkin", "Kyle Worley", "Phylicia Masonheimer", "Laura Wifler",
    # Tier 3 — existing
    "Karen Swallow Prior", "Tish Harrison Warren", "Jake Meador (Mere Orthodoxy)",
    "Samuel James", "Alan Jacobs", "Carey Nieuwhof",
    # Tier 3 — network discovery additions
    "Russell Moore", "Scot McKnight", "Andy Crouch", "Carl Trueman",
    "Matthew Lee Anderson", "O. Alan Noble", "Ryan Burge",
    "Sam Allberry", "Trillia Newbell", "Joy Clarkson", "Mike Cosper",
    "Bethel McGrew", "Bonnie Kristian", "Aimee Byrd", "Nadya Williams",
    "Daniel K. Williams", "Tsh Oxenreider", "Gary Thomas", "Spencer Klavan",
    "Diane Langberg", "Timothy Paul Jones", "BibleProject",
    "Kate Shellnutt", "Jonathon Seidl",
}
MIN_INDEPENDENT_ARTICLES = 3
INDEPENDENT_FLOOR_BOOST  = 2.0  # boost applied to top independents if floor not met

def source_max(source_name: str) -> int:
    if source_name in TIER_1A_SOURCES or source_name in TIER_1_SOURCES:
        return 5
    if source_name in TIER_2_SOURCES:
        return 3
    return 2  # Tier 3 substacks and Tier 4 world news

PREVIOUSLY_SHOWN_PENALTY = 4.0   # applied to articles already surfaced on the site
DUPLICATE_TOPIC_PENALTY   = 3.0   # applied to same-topic same-perspective duplicates
OPPOSING_VIEWS_BOOST      = 1.0   # applied to articles that form an opposing pair

# Catholic content: cluster keywords that trigger a hard score cap of 3
# (applied after Claude scoring so it works even if Claude scores too high)
CATHOLIC_CLUSTER_KEYWORDS = {
    "pope", "papal", "vatican", "synod", "synodality", "cardinal", "jesuit",
    "catholic_church", "roman_catholic", "pope_francis", "holy_see",
    "encyclical", "bishop_of_rome", "purgatory", "catholic",
}
CATHOLIC_SCORE_CAP = 3.0  # max final_score for Catholic-specific content


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


def apply_independent_floor(articles: list[dict], top_n: int = 20) -> list[dict]:
    """Guarantee at least MIN_INDEPENDENT_ARTICLES from independent author sources
    appear in the top_n results. If the floor isn't met, boost the highest-scoring
    independents that fell below the cutoff so they rise into contention.
    """
    top = articles[:top_n]
    rest = articles[top_n:]

    independent_in_top = sum(
        1 for a in top if a.get("source_name") in INDEPENDENT_SOURCES
    )

    if independent_in_top >= MIN_INDEPENDENT_ARTICLES:
        return articles  # floor already met

    needed = MIN_INDEPENDENT_ARTICLES - independent_in_top
    # Find the best-scoring independents sitting outside the top_n
    candidates = sorted(
        [a for a in rest if a.get("source_name") in INDEPENDENT_SOURCES],
        key=lambda x: x["final_score"], reverse=True
    )
    boosted = 0
    for a in candidates:
        if boosted >= needed:
            break
        a["final_score"] = round(min(a["final_score"] + INDEPENDENT_FLOOR_BOOST, 10.0), 2)
        a["independent_floor_boosted"] = True
        boosted += 1

    if boosted:
        print(f"  Independent floor: boosted {boosted} independent articles to meet minimum of {MIN_INDEPENDENT_ARTICLES}.")

    # Re-sort after boosts
    return sorted(articles, key=lambda a: a["final_score"], reverse=True)


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

    # Step 0b: Hard cutoff — drop articles older than HARD_CUTOFF_DAYS
    cutoff_hours = HARD_CUTOFF_DAYS * 24
    fresh = []
    dropped_old = 0
    for a in articles:
        published = a.get("published", "")
        if published:
            try:
                pub_dt = parsedate_to_datetime(published)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                hours_old = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
                if hours_old > cutoff_hours:
                    dropped_old += 1
                    continue
            except Exception:
                pass
        fresh.append(a)
    if dropped_old:
        print(f"  Hard cutoff: dropped {dropped_old} articles older than {HARD_CUTOFF_DAYS} days.")
    articles = fresh

    # Step 1: Claude scoring in batches
    scored = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        print(f"  Scoring articles {i+1}-{min(i+BATCH_SIZE, len(articles))}...")
        scored.extend(score_batch(batch))

    # Step 2: Apply source tier multiplier + recency boost → store in final_score
    shown_urls = shown_urls or set()
    previously_shown_count = 0
    catholic_capped_count = 0
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

        # Apply Catholic content cap: check topic_cluster and title for Catholic keywords
        cluster = (article.get("topic_cluster") or "").lower()
        title = (article.get("title") or "").lower()
        is_catholic = any(kw in cluster or kw in title for kw in CATHOLIC_CLUSTER_KEYWORDS)
        if is_catholic and raw_final > CATHOLIC_SCORE_CAP:
            raw_final = CATHOLIC_SCORE_CAP
            article["catholic_capped"] = True
            catholic_capped_count += 1

        article["final_score"] = raw_final
        if boost > 0:
            article["recency_boost"] = boost

    if previously_shown_count:
        print(f"  Applied previously-shown penalty to {previously_shown_count} articles.")
    if catholic_capped_count:
        print(f"  Applied Catholic content cap to {catholic_capped_count} articles.")

    # Step 3: Sort by final_score before diversity pass
    scored.sort(key=lambda a: a["final_score"], reverse=True)

    # Step 4: Apply topic deduplication (suppress same-topic same-perspective duplicates,
    #          boost opposing viewpoint pairs)
    scored = apply_topic_deduplication(scored)

    # Step 5: Apply source diversity penalty and hard cap
    scored = apply_diversity_penalty(scored)

    # Step 6: Re-sort after diversity pass
    scored.sort(key=lambda a: a["final_score"], reverse=True)

    # Step 7: Independent author floor — guarantee at least 3 independent articles
    scored = apply_independent_floor(scored)

    return scored
