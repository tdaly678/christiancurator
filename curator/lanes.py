"""
lanes.py: selection helpers for the two front-page lanes (P1, 2026-10-30).

The importance lane (front page, lead, Other Headlines, World News, email) is
the existing final_score ordering. The "Worth Your Time" lane is chosen here by
depth. Kept free of API clients so render-only scripts can import it without
ANTHROPIC_API_KEY.
"""

WORTH_YOUR_TIME_COUNT = 5
WORTH_YOUR_TIME_MIN_DEPTH = 6.0


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
