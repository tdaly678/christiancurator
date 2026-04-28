"""
trending.py — detect trending topics in evangelical discourse and produce a
boost map the scorer can apply to today's fetch.

Four signal sources, blended in order:

  1. INTERNAL CORPUS (always-on, deterministic)
     For each topic_cluster across the recent fetch + article_history.json,
     compute three signals:
       - breadth: unique sources publishing on the topic in the last 7 days
       - velocity: 7-day count vs. trailing 30-day daily average
       - tier_heat: tier-weighted contribution (Tier 1 outlets count more)
     Topics need breadth >= 3 to be considered "trending" — a single outlet
     on a hobbyhorse doesn't qualify.

  2. WIKIPEDIA PAGEVIEWS (always-on, no auth needed)
     Wikimedia's free pageviews API measures public curiosity around topic
     keywords. A spike in page views (recent 7d vs. 30d baseline) signals
     broader cultural interest, not just editorial coverage. Runs after
     internal scoring so it can amplify topics already on the radar.

  3. REDDIT (optional, gracefully degrades to no-op)
     Evangelical and Christian subreddits surface grassroots discourse.
     Requires REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (free app registration).
     If creds are absent, this no-ops cleanly.

  4. BLUESKY (optional, gracefully degrades to no-op)
     Post-Twitter evangelical chatter has migrated partly to Bluesky. Requires
     BLUESKY_HANDLE + BLUESKY_APP_PASSWORD. No-ops cleanly without creds.

  5. X / SOCIAL LISTENING (optional, gracefully degrades to no-op)
     If X_BEARER_TOKEN is set, query X recent-search for evangelical-flavored
     keywords. NOTE: X API access requires a paid tier as of Feb 2026; this
     amplifier is present but effectively dormant unless the token is supplied.

Boost output (per topic_cluster):
  - "warm"  → +0.75   (3-4 sources, modest velocity)
  - "hot"   → +1.00   (5-6 sources OR strong velocity)
  - "fire"  → +1.50   (7+ sources AND velocity >= 2x baseline)

Heat bumps from amplifiers stack but are capped at "fire" (+1.50).
The scorer applies the boost to articles whose topic_cluster matches.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

logger = logging.getLogger(__name__)

# ── Tunables ──────────────────────────────────────────────────────────────────
TRENDING_RECENT_WINDOW_DAYS = 7    # window for "what's trending right now"
TRENDING_BASELINE_WINDOW_DAYS = 30  # window for the velocity baseline
TRENDING_MIN_BREADTH = 3            # need this many unique sources to qualify

# Heat tiers: (label, min_breadth, min_velocity_ratio, boost)
HEAT_TIERS = [
    ("fire", 7, 2.0, 1.50),
    ("hot",  5, 1.5, 1.00),
    ("warm", 3, 1.2, 0.75),
]

HEAT_ORDER = ["warm", "hot", "fire"]
BOOST_LOOKUP = {label: boost for label, _, _, boost in HEAT_TIERS}

# Tier weighting for breadth/heat — Tier 1A coverage of a topic carries more
# signal than three Substacks rehashing the same news. Mirrors scorer tiers.
SOURCE_TIER_WEIGHTS = {
    # Tier 1A
    "The Gospel Coalition": 1.5,
    "Desiring God": 1.5,
    "Ligonier Ministries": 1.5,
    "9Marks": 1.5,
    # Tier 1
    "Christianity Today": 1.4,
    "First Things": 1.4,
    "Crossway": 1.4,
    "Mere Orthodoxy": 1.4,
    "American Reformer": 1.4,
}
DEFAULT_SOURCE_WEIGHT = 1.0


def _normalize_cluster(cluster: str | None) -> str:
    """Topic clusters are user-readable strings — normalize for grouping."""
    if not cluster:
        return ""
    return cluster.strip().lower().replace("_", " ").replace("-", " ")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (ValueError, TypeError):
        return None


def _load_history(history_path: str) -> list[dict]:
    if not os.path.exists(history_path):
        return []
    try:
        with open(history_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _classify_heat(breadth: float, velocity: float) -> tuple[str | None, float]:
    """Return (heat_label, boost_amount) — strongest matching tier wins."""
    for label, min_breadth, min_velocity, boost in HEAT_TIERS:
        if breadth >= min_breadth and velocity >= min_velocity:
            return label, boost
    return None, 0.0


def _bump_heat(info: dict, tiers: int) -> None:
    """Bump the heat tier of a trending entry by `tiers` steps, capped at fire.

    Mutates info in-place; callers set the *_amplified flag themselves.
    """
    current = info.get("heat")
    if not current or current not in HEAT_ORDER:
        return
    current_idx = HEAT_ORDER.index(current)
    new_idx = min(current_idx + tiers, len(HEAT_ORDER) - 1)
    new_heat = HEAT_ORDER[new_idx]
    info["heat"] = new_heat
    info["boost"] = BOOST_LOOKUP[new_heat]


def compute_internal_trending(
    today_articles: list[dict],
    history_path: str = "docs/article_history.json",
    today: date | None = None,
) -> dict[str, dict]:
    """Compute trending scores from internal corpus only.

    Returns: {normalized_cluster: {
        "breadth": int (unique sources, weighted),
        "velocity": float (7d vs 30d daily baseline ratio),
        "heat": "warm" | "hot" | "fire" | None,
        "boost": float,
        "source_count_7d": int (raw, unweighted),
        "tier_heat": float,
    }}
    """
    today = today or date.today()
    recent_cutoff = today - timedelta(days=TRENDING_RECENT_WINDOW_DAYS)
    baseline_cutoff = today - timedelta(days=TRENDING_BASELINE_WINDOW_DAYS)

    history = _load_history(history_path)

    # Build per-cluster aggregates from history (only articles we've actually
    # surfaced). Today's fetch contributes too — even unsurfaced — so we can
    # detect topics the algorithm hasn't yet rewarded.
    by_cluster: dict[str, dict] = defaultdict(
        lambda: {"recent_sources": set(), "recent_count": 0,
                 "baseline_count": 0, "tier_heat": 0.0}
    )

    for entry in history:
        cluster = _normalize_cluster(entry.get("topic_cluster") or entry.get("cluster"))
        # article_history doesn't always carry topic_cluster — skip when missing
        if not cluster:
            continue
        d = _parse_date(entry.get("date_shown"))
        if not d or d < baseline_cutoff:
            continue
        src = entry.get("source_name", "")
        if d >= recent_cutoff:
            by_cluster[cluster]["recent_sources"].add(src)
            by_cluster[cluster]["recent_count"] += 1
            by_cluster[cluster]["tier_heat"] += SOURCE_TIER_WEIGHTS.get(src, DEFAULT_SOURCE_WEIGHT)
        by_cluster[cluster]["baseline_count"] += 1

    # Today's fetch — counts toward "recent" only
    for art in today_articles:
        cluster = _normalize_cluster(art.get("topic_cluster"))
        if not cluster:
            continue
        src = art.get("source_name", "")
        by_cluster[cluster]["recent_sources"].add(src)
        by_cluster[cluster]["recent_count"] += 1
        by_cluster[cluster]["tier_heat"] += SOURCE_TIER_WEIGHTS.get(src, DEFAULT_SOURCE_WEIGHT)
        by_cluster[cluster]["baseline_count"] += 1

    out: dict[str, dict] = {}
    baseline_days = TRENDING_BASELINE_WINDOW_DAYS
    recent_days = TRENDING_RECENT_WINDOW_DAYS

    for cluster, agg in by_cluster.items():
        breadth = len(agg["recent_sources"])
        if breadth < TRENDING_MIN_BREADTH:
            continue
        # Velocity = (recent rate) / (baseline rate). Baseline rate uses the
        # full 30-day window so a topic with 4 articles in 7d vs. 4 in 30d
        # registers ~4x velocity. Avoid divide-by-zero by treating <1 as 1.
        baseline_per_day = max(agg["baseline_count"] / baseline_days, 1 / baseline_days)
        recent_per_day = agg["recent_count"] / recent_days
        velocity = recent_per_day / baseline_per_day

        # Folding tier_heat in via a small breadth bonus — a Tier 1A source
        # in the mix counts as ~1.5 sources for heat-tier classification.
        weighted_breadth = agg["tier_heat"] / max(1.0, agg["recent_count"] / breadth)

        heat, boost = _classify_heat(weighted_breadth, velocity)
        if heat:
            out[cluster] = {
                "breadth": breadth,
                "weighted_breadth": round(weighted_breadth, 2),
                "velocity": round(velocity, 2),
                "heat": heat,
                "boost": boost,
                "source_count_7d": agg["recent_count"],
                "tier_heat": round(agg["tier_heat"], 2),
                "sources": sorted(agg["recent_sources"]),
            }
    return out


# ── Wikipedia pageviews amplifier (always-on, no auth needed) ─────────────────
# Wikimedia's REST API returns daily pageview counts for any Wikipedia article.
# We compare a 7-day recent window against a 30-day baseline to detect spikes.
# Useful for topics that suddenly break into mainstream conversation — a surge
# in "Christian nationalism" Wikipedia traffic correlates strongly with news cycles
# that haven't yet fully percolated into evangelical outlet coverage.

WIKI_PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    "/en.wikipedia/all-access/all-agents/{title}/daily/{start}/{end}"
)

# Maps normalized cluster phrases → lists of Wikipedia page titles.
# Prefer canonical, high-traffic pages over narrow ones — narrow pages get too
# few baseline views to produce meaningful spike ratios.
# Keys MUST match _normalize_cluster() output (lowercase, spaces not hyphens).
CLUSTER_TO_WIKI_PAGES: dict[str, list[str]] = {
    # Core Theology
    "atonement": ["Atonement_in_Christianity"],
    "justification by faith": ["Justification_(theology)"],
    "biblical inerrancy": ["Biblical_inerrancy"],
    "inerrancy": ["Biblical_inerrancy"],
    "baptism": ["Baptism"],
    "lords supper": ["Eucharist"],
    "eucharist": ["Eucharist"],
    "communion": ["Eucharist"],
    "heaven hell eternity": ["Hell", "Heaven_in_Christianity"],
    "heaven and hell": ["Hell", "Heaven_in_Christianity"],
    "hell": ["Hell"],
    "creation evolution": ["Creationism", "Theistic_evolution"],
    "creationism": ["Creationism"],
    "evolution": ["Evolution"],
    "intelligent design": ["Intelligent_design"],
    "suffering and providence": ["Theodicy", "Divine_providence"],
    "theodicy": ["Theodicy"],
    "providence": ["Divine_providence"],
    "gender and biblical anthropology": ["Gender", "Transgender"],
    "transgender": ["Transgender"],
    "gender identity": ["Gender_identity"],
    "apologetics": ["Christian_apologetics"],
    "christian nationalism": ["Christian_nationalism"],
    "nationalism": ["Christian_nationalism"],
    "complementarianism egalitarianism": ["Complementarianism", "Christian_egalitarianism"],
    "complementarianism": ["Complementarianism"],
    "egalitarianism": ["Christian_egalitarianism"],
    "women in ministry": ["Women_in_Christianity"],
    "sanctification": ["Sanctification"],
    "christology": ["Christology"],
    "covenant theology": ["Covenant_theology"],
    "deconstruction": ["Faith_deconstruction"],
    "faith deconstruction": ["Faith_deconstruction"],
    # Church Life
    "church discipline": ["Church_discipline"],
    "worship and liturgy": ["Christian_worship", "Liturgy"],
    "worship": ["Christian_worship"],
    "liturgy": ["Liturgy"],
    "local church": ["Local_church"],
    "missions and evangelism": ["Christian_mission", "Evangelism"],
    "evangelism": ["Evangelism"],
    "missions": ["Christian_mission"],
    "church history": ["History_of_Christianity"],
    "church membership": ["Church_membership"],
    "church planting": ["Church_planting"],
    "preaching": ["Preaching"],
    "prayer": ["Prayer_in_Christianity"],
    "discipleship": ["Discipleship"],
    "spiritual disciplines": ["Spiritual_discipline"],
    "spiritual warfare": ["Spiritual_warfare"],
    "fasting": ["Fasting"],
    "small groups": ["Small_group_ministry"],
    "pastoral ministry": ["Ministry_(Christianity)"],
    "church governance": ["Church_governance"],
    # Spiritual Formation
    "anxiety and fear": ["Anxiety"],
    "mental health": ["Mental_health"],
    "mental health and faith": ["Mental_health"],
    "singleness": ["Celibacy_in_Christianity"],
    "death and dying": ["Death"],
    # Culture & Society
    "politics and the church": ["Christianity_and_politics"],
    "politics": ["Christianity_and_politics"],
    "racial reconciliation": ["Racial_reconciliation"],
    "racism": ["Racism"],
    "technology": ["Technology"],
    "technology and the christian life": ["Technology"],
    "biblical literacy": ["Bible_literacy"],
    "pornography": ["Pornography"],
    "pornography and sexual purity": ["Pornography"],
    "abortion": ["Abortion"],
    "pro life": ["Abortion"],
    "addiction and recovery": ["Addiction"],
    "addiction": ["Addiction"],
    "creation care": ["Creation_care"],
    "christian masculinity": ["Masculinity"],
    "masculinity": ["Masculinity"],
    "stewardship and generosity": ["Stewardship_(theology)"],
    "stewardship": ["Stewardship_(theology)"],
    "christian education": ["Christian_education"],
}


def _wiki_daily_avg(title: str, start: date, end: date) -> float:
    """Fetch total Wikipedia pageviews for `title` over [start, end].

    Returns average daily views, or 0.0 on any error. Never raises.
    """
    try:
        import requests  # already in requirements.txt
    except ImportError:
        return 0.0
    url = WIKI_PAGEVIEWS_URL.format(
        title=title,
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "ChristianCurator/1.0 (https://christiancurator.com)"},
            timeout=10,
        )
        if resp.status_code != 200:
            return 0.0
        items = resp.json().get("items", [])
        if not items:
            return 0.0
        total = sum(item.get("views", 0) for item in items)
        days = max((end - start).days, 1)
        return total / days
    except Exception:
        return 0.0


def amplify_with_wikipedia(
    internal_trending: dict[str, dict],
) -> dict[str, dict]:
    """Layer Wikipedia pageview spikes onto internal trending scores.

    Always runs — no auth required. Fetches recent (7d) vs. baseline (30d)
    pageview averages for Wikipedia pages mapped to each trending cluster.
    A spike ratio ≥ 3x bumps heat one tier; ≥ 5x bumps two tiers.
    """
    today = date.today()
    recent_end = today - timedelta(days=1)   # yesterday (today incomplete)
    recent_start = today - timedelta(days=7)
    baseline_end = today - timedelta(days=1)
    baseline_start = today - timedelta(days=30)

    for cluster, info in internal_trending.items():
        pages = CLUSTER_TO_WIKI_PAGES.get(cluster)
        if not pages:
            # Try partial match — cluster "christian nationalism" hits the key directly,
            # but scorer may emit "christian_nationalism" which normalizes identically.
            # If still no hit, skip rather than guess a bad page.
            info["wiki_amplified"] = False
            continue

        recent_total, baseline_total = 0.0, 0.0
        for page in pages:
            recent_total += _wiki_daily_avg(page, recent_start, recent_end)
            baseline_total += _wiki_daily_avg(page, baseline_start, baseline_end)

        info["wiki_pageviews_recent"] = round(recent_total, 1)
        info["wiki_pageviews_baseline"] = round(baseline_total, 1)

        # Spike ratio: how much faster are people reading these pages lately?
        # Guard against near-zero baselines (obscure topics) — a 5-view spike
        # on a page that averages 2 views/day isn't meaningful signal.
        if baseline_total >= 10:
            spike = recent_total / baseline_total
        else:
            spike = 1.0  # insufficient baseline — treat as no signal
        info["wiki_spike"] = round(spike, 2)

        bump = 2 if spike >= 5.0 else (1 if spike >= 3.0 else 0)
        if bump > 0:
            _bump_heat(info, bump)
            info["wiki_amplified"] = True
        else:
            info["wiki_amplified"] = False

    return internal_trending


# ── Reddit amplifier (optional — requires free app credentials) ───────────────
# r/Christianity, r/Reformed, etc. surface grassroots discourse that editorial
# outlets haven't yet picked up. High post counts on a topic within a week
# suggest organic momentum, not just PR-driven coverage cycles.

EVANGELICAL_SUBREDDITS = [
    "Christianity", "Reformed", "TrueChristian", "Christian",
    "Bible", "AskAChristian", "OpenChristian", "Catholicism",
]
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_SEARCH_URL = "https://oauth.reddit.com/r/{subreddit}/search.json"

# Module-level cache so we only auth once per pipeline run
_reddit_token_cache: dict[str, str] = {}


def _get_reddit_token(client_id: str, client_secret: str) -> str | None:
    """Exchange client credentials for a bearer token. Cached for the run."""
    cache_key = client_id
    if cache_key in _reddit_token_cache:
        return _reddit_token_cache[cache_key]
    try:
        import requests
    except ImportError:
        return None
    owner = os.environ.get("REDDIT_USER_AGENT_OWNER", "tdaly678")
    try:
        resp = requests.post(
            REDDIT_TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": f"ChristianCurator/1.0 by /u/{owner}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        token = resp.json().get("access_token")
        if token:
            _reddit_token_cache[cache_key] = token
        return token
    except Exception:
        return None


def _reddit_cluster_signal(cluster: str, token: str) -> tuple[int, int]:
    """Search evangelical subreddits for `cluster`; return (post_count, upvotes).

    Returns (0, 0) on any error — callers should be tolerant of failure.
    """
    try:
        import requests
    except ImportError:
        return 0, 0

    owner = os.environ.get("REDDIT_USER_AGENT_OWNER", "tdaly678")
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": f"ChristianCurator/1.0 by /u/{owner}",
    }
    total_posts, total_upvotes = 0, 0
    for subreddit in EVANGELICAL_SUBREDDITS:
        try:
            resp = requests.get(
                REDDIT_SEARCH_URL.format(subreddit=subreddit),
                headers=headers,
                params={
                    "q": f'"{cluster}"',
                    "restrict_sr": 1,
                    "t": "week",
                    "sort": "relevance",
                    "limit": 25,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            children = resp.json().get("data", {}).get("children", [])
            for child in children:
                post = child.get("data", {})
                total_posts += 1
                total_upvotes += post.get("ups", 0)
        except Exception:
            continue  # one subreddit failing shouldn't abort the rest

    return total_posts, total_upvotes


def amplify_with_reddit(
    internal_trending: dict[str, dict],
    client_id: str | None = None,
    client_secret: str | None = None,
) -> dict[str, dict]:
    """Layer Reddit post signal onto internal trending scores.

    No-op when REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are absent.
    ≥10 posts or ≥500 upvotes across subreddits → bump one tier.
    ≥25 posts or ≥2000 upvotes → bump two tiers.
    """
    client_id = client_id or os.environ.get("REDDIT_CLIENT_ID")
    client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.debug("amplify_with_reddit: skipped — REDDIT_CLIENT_ID/SECRET not set")
        return internal_trending

    token = _get_reddit_token(client_id, client_secret)
    if not token:
        logger.warning("amplify_with_reddit: skipped — could not obtain access token")
        return internal_trending

    for cluster, info in internal_trending.items():
        posts, upvotes = _reddit_cluster_signal(cluster, token)
        info["reddit_posts"] = posts
        info["reddit_upvotes"] = upvotes

        bump = 0
        if posts >= 25 or upvotes >= 2000:
            bump = 2
        elif posts >= 10 or upvotes >= 500:
            bump = 1

        if bump > 0:
            _bump_heat(info, bump)
            info["reddit_amplified"] = True
        else:
            info["reddit_amplified"] = False

    return internal_trending


# ── Bluesky amplifier (optional — requires free app password) ─────────────────
# Post-Twitter evangelical discourse has meaningfully shifted to Bluesky.
# The searchPosts endpoint (polling, not firehose) is the right primitive
# for a daily-digest pipeline — lightweight, predictable, no WebSocket overhead.

BLUESKY_SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
BLUESKY_SEARCH_URL = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"

# Module-level cache so we auth once per run
_bluesky_jwt_cache: dict[str, str] = {}


def _get_bluesky_jwt(handle: str, app_password: str) -> str | None:
    """Create a Bluesky session and return the accessJwt. Cached for the run."""
    if handle in _bluesky_jwt_cache:
        return _bluesky_jwt_cache[handle]
    try:
        import requests
    except ImportError:
        return None
    try:
        resp = requests.post(
            BLUESKY_SESSION_URL,
            json={"identifier": handle, "password": app_password},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        jwt = resp.json().get("accessJwt")
        if jwt:
            _bluesky_jwt_cache[handle] = jwt
        return jwt
    except Exception:
        return None


def amplify_with_bluesky(
    internal_trending: dict[str, dict],
    handle: str | None = None,
    app_password: str | None = None,
) -> dict[str, dict]:
    """Layer Bluesky post counts onto internal trending scores.

    No-op when BLUESKY_HANDLE / BLUESKY_APP_PASSWORD are absent.
    Uses the searchPosts polling endpoint — NOT the firehose WebSocket.
    ≥30 posts in last 7d → bump one tier; ≥100 posts → bump two tiers.
    """
    handle = handle or os.environ.get("BLUESKY_HANDLE")
    app_password = app_password or os.environ.get("BLUESKY_APP_PASSWORD")

    if not handle or not app_password:
        logger.debug("amplify_with_bluesky: skipped — BLUESKY_HANDLE/APP_PASSWORD not set")
        return internal_trending

    jwt = _get_bluesky_jwt(handle, app_password)
    if not jwt:
        logger.warning("amplify_with_bluesky: skipped — could not create Bluesky session")
        return internal_trending

    try:
        import requests
    except ImportError:
        return internal_trending

    since_iso = (date.today() - timedelta(days=7)).isoformat() + "T00:00:00Z"
    headers = {"Authorization": f"Bearer {jwt}"}

    for cluster, info in internal_trending.items():
        try:
            resp = requests.get(
                BLUESKY_SEARCH_URL,
                headers=headers,
                params={"q": f'"{cluster}"', "since": since_iso, "limit": 100},
                timeout=10,
            )
            if resp.status_code != 200:
                info["bluesky_posts"] = 0
                info["bluesky_amplified"] = False
                continue
            posts = len(resp.json().get("posts", []))
        except Exception:
            info["bluesky_posts"] = 0
            info["bluesky_amplified"] = False
            continue

        info["bluesky_posts"] = posts

        bump = 2 if posts >= 100 else (1 if posts >= 30 else 0)
        if bump > 0:
            _bump_heat(info, bump)
            info["bluesky_amplified"] = True
        else:
            info["bluesky_amplified"] = False

    return internal_trending


# ── X / Social listening (optional) ───────────────────────────────────────────
# Gracefully no-ops when X_BEARER_TOKEN isn't configured. NOTE: X API free
# tier was removed in Feb 2026 — this amplifier is present for completeness
# but effectively dormant without a paid bearer token.

X_RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
X_QUERY_TERMS_PER_CLUSTER = 3   # how many keywords per cluster to test
X_MAX_RESULTS = 100             # X API per-call max

# Mention thresholds for X-driven heat amplification
X_AMPLIFY_TIERS = [
    (500, 1),   # 500+ recent mentions → bump heat by 1 tier
    (100, 0),   # 100+ mentions → no bump but contributes to evidence
]


def fetch_x_mentions(query: str, bearer_token: str, max_results: int = X_MAX_RESULTS) -> int:
    """Hit X recent-search for `query`, return raw mention count.

    Returns 0 on any error so we degrade gracefully. NEVER raises — the caller
    should always be able to ignore failure and proceed with internal signals.
    """
    try:
        import requests  # type: ignore
    except ImportError:
        return 0
    try:
        resp = requests.get(
            X_RECENT_SEARCH_URL,
            headers={"Authorization": f"Bearer {bearer_token}"},
            params={"query": query, "max_results": min(max_results, 100),
                    "tweet.fields": "public_metrics"},
            timeout=10,
        )
        if resp.status_code != 200:
            return 0
        data = resp.json()
        return data.get("meta", {}).get("result_count", 0)
    except Exception:
        return 0


def amplify_with_x(
    internal_trending: dict[str, dict],
    bearer_token: str | None = None,
) -> dict[str, dict]:
    """Layer X mention counts onto internal trending scores.

    No-op when bearer_token is missing/empty. Mutates and returns the dict;
    adds 'x_mentions' and may bump 'heat' / 'boost' upward by one tier when
    cross-platform momentum is strong.
    """
    bearer_token = bearer_token or os.environ.get("X_BEARER_TOKEN")
    if not bearer_token:
        return internal_trending  # graceful no-op

    for cluster, info in internal_trending.items():
        # Build a query from the cluster phrase. Quote multi-word clusters so
        # "christian nationalism" matches as a phrase, not as separate tokens.
        query = f'"{cluster}" lang:en -is:retweet'
        mentions = fetch_x_mentions(query, bearer_token)
        info["x_mentions"] = mentions

        bump_tiers = 0
        for threshold, bump in X_AMPLIFY_TIERS:
            if mentions >= threshold:
                bump_tiers = bump
                break
        if bump_tiers > 0:
            _bump_heat(info, bump_tiers)
            info["x_amplified"] = True

    return internal_trending


# ── Public API ────────────────────────────────────────────────────────────────

def compute_trending(
    today_articles: list[dict],
    history_path: str = "docs/article_history.json",
    use_x: bool = True,
) -> dict[str, dict]:
    """Compute the full trending map (internal + all optional amplifiers).

    Amplifier order matters — each can stack onto the previous. Wikipedia runs
    first (always-on), then Reddit, Bluesky, and finally X (all conditional).
    Final heat is capped at "fire" (+1.50) inside each _bump_heat call.

    Returns {normalized_cluster: trending_info_dict}.
    """
    trending = compute_internal_trending(today_articles, history_path)
    trending = amplify_with_wikipedia(trending)   # always runs — no auth
    trending = amplify_with_reddit(trending)       # no-op if no creds
    trending = amplify_with_bluesky(trending)      # no-op if no creds
    if use_x:
        trending = amplify_with_x(trending)        # no-op if no creds (paid tier)
    return trending


def trending_boost_for(article: dict, trending: dict[str, dict]) -> float:
    """Look up the boost amount for a single article based on its topic_cluster.
    Returns 0.0 if the cluster isn't trending."""
    cluster = _normalize_cluster(article.get("topic_cluster"))
    if not cluster:
        return 0.0
    info = trending.get(cluster)
    return info["boost"] if info else 0.0


def format_trending_summary(trending: dict[str, dict]) -> list[str]:
    """Human-readable lines for pipeline log output, hottest first.

    Shows whichever external signals fired for each cluster.
    """
    lines: list[str] = []
    sorted_clusters = sorted(
        trending.items(),
        key=lambda kv: (kv[1]["boost"], kv[1].get("velocity", 0)),
        reverse=True,
    )
    for cluster, info in sorted_clusters:
        signals = []

        if "x_mentions" in info:
            note = f"X={info['x_mentions']}"
            if info.get("x_amplified"):
                note += "[+1↑]"
            signals.append(note)

        if "reddit_posts" in info:
            note = f"Reddit={info['reddit_posts']}posts/{info.get('reddit_upvotes', 0)}↑"
            if info.get("reddit_amplified"):
                note += "[+1↑]"
            signals.append(note)

        if "wiki_spike" in info:
            note = f"Wiki={info['wiki_spike']}x"
            if info.get("wiki_amplified"):
                note += "[+1↑]"
            signals.append(note)

        if "bluesky_posts" in info:
            note = f"Bluesky={info['bluesky_posts']}"
            if info.get("bluesky_amplified"):
                note += "[+1↑]"
            signals.append(note)

        signal_str = ", ".join(signals)
        if signal_str:
            signal_str = f", {signal_str}"

        lines.append(
            f"    [{info['heat'].upper()}] +{info['boost']:.2f}  {cluster}  "
            f"(breadth={info['breadth']}, velocity={info['velocity']}x{signal_str})"
        )
    return lines
