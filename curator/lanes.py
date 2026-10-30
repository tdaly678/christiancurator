"""
lanes.py: selection helpers for the front-page lanes (P1, 2026-10-30).

The importance lane (front page, lead, Other Headlines, World News, email) is
the existing final_score ordering. The "Worth Your Time" lane is chosen here by
depth, and the "Watch and Listen" lane (Wave 3) from the media feeds by recency
and source priority. Kept free of API clients so render-only scripts can import
it without ANTHROPIC_API_KEY.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from curator.dedup import canonical_url
from fetcher.sources import SOURCES

WORTH_YOUR_TIME_COUNT = 5
WORTH_YOUR_TIME_MIN_DEPTH = 6.0

WATCH_LISTEN_MAX = 5
WATCH_LISTEN_MIN = 3          # fewer qualifying items: omit the section
WATCH_LISTEN_MAX_AGE_DAYS = 7
WATCH_LISTEN_FRESH_DAYS = 2   # items this new outrank older ones regardless of priority

# Editorial priority = order of the media sources in fetcher/sources.py.
MEDIA_PRIORITY = {s["name"]: i for i, s in enumerate(x for x in SOURCES if x.get("role") == "media")}


def select_worth_your_time(
    articles: list[dict],
    exclude_urls: set | None = None,
    n: int = WORTH_YOUR_TIME_COUNT,
    exclude_top_n: int = 10,
    min_depth: float = WORTH_YOUR_TIME_MIN_DEPTH,
) -> list[dict]:
    """Top `n` non-world-news articles by depth, one per source.

    Skips anything in `exclude_urls` (pass the front-page and Other Headlines
    URLs) or, when no set is given, the top `exclude_top_n` by importance, so
    the two lanes don't repeat each other. Previously shown and Catholic-capped
    items are skipped, as is anything below `min_depth`.
    """
    pool = [a for a in articles if a.get("source_type") != "world_news"]
    if exclude_urls is None:
        ranked = sorted(pool, key=lambda a: a.get("final_score", 0), reverse=True)
        exclude_urls = {a.get("url") for a in ranked[:exclude_top_n]}
    candidates = sorted(
        (a for a in pool
         if a.get("url") and a.get("url") not in exclude_urls
         and not a.get("previously_shown") and not a.get("catholic_capped")
         and float(a.get("depth") or 0) >= min_depth),
        key=lambda a: (a.get("depth") or 0, a.get("base_depth") or 0, a.get("final_score") or 0),
        reverse=True,
    )
    picks, sources = [], set()
    for a in candidates:
        src = a.get("source_name", "")
        if src in sources:
            continue
        picks.append(a)
        sources.add(src)
        if len(picks) >= n:
            break
    return picks


def _published(a: dict) -> datetime | None:
    try:
        dt = parsedate_to_datetime(a.get("published") or "")
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def select_watch_and_listen(
    media_items: list[dict],
    exclude_urls: set | None = None,
    n: int = WATCH_LISTEN_MAX,
    min_items: int = WATCH_LISTEN_MIN,
    max_age_days: int = WATCH_LISTEN_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> list[dict]:
    """Up to `n` video/podcast items from the media feeds, one per source.

    Candidates are published in the last `max_age_days`, not previously shown
    (main.py sets previously_shown from article_history.json) and not already
    placed elsewhere on the page. Each source offers its newest candidate; items
    from the last WATCH_LISTEN_FRESH_DAYS come first, then source priority, then
    recency. When both formats qualify the lane keeps at least one of each.
    Returns [] when fewer than `min_items` qualify.
    """
    now = now or datetime.now(timezone.utc)
    excluded = {canonical_url(u) for u in (exclude_urls or set())}
    newest_by_source: dict = {}
    for a in media_items or []:
        dt = _published(a)
        if not a.get("url") or dt is None or a.get("previously_shown"):
            continue
        age_days = (now - dt).total_seconds() / 86400
        if age_days > max_age_days or canonical_url(a["url"]) in excluded:
            continue
        src = a.get("source_name", "")
        best = newest_by_source.get(src)
        if best is None or dt > best[0]:
            newest_by_source[src] = (dt, age_days, a)

    ranked = sorted(
        newest_by_source.values(),
        key=lambda t: (t[1] > WATCH_LISTEN_FRESH_DAYS,
                       MEDIA_PRIORITY.get(t[2].get("source_name", ""), len(MEDIA_PRIORITY)),
                       -t[0].timestamp()),
    )
    candidates = [t[2] for t in ranked]
    if len(candidates) < min_items:
        return []
    picks = candidates[:n]
    formats = {a.get("media_format") for a in picks}
    if len(formats) == 1:
        other = next((a for a in candidates[n:] if a.get("media_format") not in formats), None)
        if other:
            picks[-1] = other
    return picks
