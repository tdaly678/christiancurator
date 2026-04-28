"""
trending.py — detect trending topics in evangelical discourse and produce a
boost map the scorer can apply to today's fetch.

Two signal sources, blended:

  1. INTERNAL CORPUS (always-on, deterministic)
     For each topic_cluster across the recent fetch + article_history.json,
     compute three signals:
       - breadth: unique sources publishing on the topic in the last 7 days
       - velocity: 7-day count vs. trailing 30-day daily average
       - tier_heat: tier-weighted contribution (Tier 1 outlets count more)
     Topics need breadth >= 3 to be considered "trending" — a single outlet
     on a hobbyhorse doesn't qualify.

  2. X / SOCIAL LISTENING (optional, gracefully degrades to no-op)
     If X_BEARER_TOKEN is set, query X recent-search for evangelical-flavored
     keywords and named voices, then fold mention counts into trending scores.
     If the bearer token is absent or the call fails, internal-only signals
     drive the boost — no degradation in pipeline reliability.

Boost output (per topic_cluster):
  - "warm"  → +0.75   (3-4 sources, modest velocity)
  - "hot"   → +1.00   (5-6 sources OR strong velocity)
  - "fire"  → +1.50   (7+ sources AND velocity >= 2x baseline)

The scorer applies the boost to articles whose topic_cluster matches.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

# ── Tunables ──────────────────────────────────────────────────────────────────
TRENDING_RECENT_WINDOW_DAYS = 7    # window for "what's trending right now"
TRENDING_BASELINE_WINDOW_DAYS = 30  # window for the velocity baseline
TRENDING_MIN_BREADTH = 3            # need this many unique sources to qualify

# Heat tiers: (min_breadth, min_velocity_ratio, boost)
HEAT_TIERS = [
    ("fire", 7, 2.0, 1.50),
    ("hot",  5, 1.5, 1.00),
    ("warm", 3, 1.2, 0.75),
]

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


# ── X / Social listening (optional) ───────────────────────────────────────────
# Gracefully no-ops when X_BEARER_TOKEN isn't configured. When configured, fold
# X mention counts into trending scores — a topic getting 5x baseline X chatter
# can promote a "warm" topic to "hot," etc.

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

    heat_order = ["warm", "hot", "fire"]
    boost_lookup = {label: boost for label, _, _, boost in HEAT_TIERS}

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
        if bump_tiers > 0 and info.get("heat") in heat_order:
            current_idx = heat_order.index(info["heat"])
            new_idx = min(current_idx + bump_tiers, len(heat_order) - 1)
            new_heat = heat_order[new_idx]
            info["heat"] = new_heat
            info["boost"] = boost_lookup[new_heat]
            info["x_amplified"] = True

    return internal_trending


# ── Public API ────────────────────────────────────────────────────────────────

def compute_trending(
    today_articles: list[dict],
    history_path: str = "docs/article_history.json",
    use_x: bool = True,
) -> dict[str, dict]:
    """Compute the full trending map (internal + optional X amplification).
    Returns {normalized_cluster: trending_info_dict}."""
    trending = compute_internal_trending(today_articles, history_path)
    if use_x:
        trending = amplify_with_x(trending)
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
    """Human-readable lines for pipeline log output, hottest first."""
    lines: list[str] = []
    sorted_clusters = sorted(
        trending.items(),
        key=lambda kv: (kv[1]["boost"], kv[1].get("velocity", 0)),
        reverse=True,
    )
    for cluster, info in sorted_clusters:
        x_note = ""
        if "x_mentions" in info:
            x_note = f", X={info['x_mentions']}"
            if info.get("x_amplified"):
                x_note += " [amplified]"
        lines.append(
            f"    [{info['heat'].upper()}] +{info['boost']:.2f}  {cluster}  "
            f"(breadth={info['breadth']}, velocity={info['velocity']}x{x_note})"
        )
    return lines
