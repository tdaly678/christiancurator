"""
layout.py: homepage v2 section selection (P1 Wave 2, 2026-10-30).

One function, build_homepage_layout(), decides which article goes where on the
front page so render_html(), the daily email and main.py (history logging) all
see the same picks:

  lead + subleads   top 4 by importance (final_score), one per source
  debate            point/counterpoint pairs, else scorer opposing pairs
  worth_your_time   depth lane, via curator.lanes.select_worth_your_time
  watch_listen      video/podcast lane from the media feeds, via
                    curator.lanes.select_watch_and_listen (Wave 3)
  board             three columns of headlines by importance
  research          Research & Data strip (docs/research_articles.json)

No API clients here, so render-only scripts can import it.
"""

import re
from datetime import datetime
from urllib.parse import urlsplit

from curator.dedup import canonical_url
from curator.lanes import select_watch_and_listen, select_worth_your_time

SUBLEAD_COUNT = 3
BOARD_PER_COLUMN = 22
BOARD_PER_SOURCE = 3  # per column, so one prolific feed can't stack a column
DEBATE_MAX_PAIRS = 2
RESEARCH_MAX = 4
# Editorial rule: at most two podcast or video items in the importance lane
# (lead block + board). Audio and video belong in Watch and Listen.
MAIN_LANE_MAX_AUDIO_VIDEO = 2
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")

# Column keys, labels and the tags that route an article to each column.
BOARD_COLUMNS = [
    ("news", "News"),
    ("commentary", "Commentary & Debate"),
    ("church", "Church & Theology"),
]
NEWS_TAGS = {"news", "data", "politics"}
CHURCH_TAGS = {"theology", "church life", "missions", "devotional", "prayer", "apologetics"}
CHURCH_SOURCE_CATEGORIES = {"theology", "devotional"}


def _score(a: dict) -> float:
    return a.get("final_score", a.get("score", 0)) or 0


def board_column(a: dict) -> str:
    """Route an article to a board column from fields the scorer already sets.

    News: world-news sources, perspective "news", or a news/data/politics tag.
    Church & Theology: a theology/church/missions/devotional tag, or a
    theology/devotional source. Everything else is commentary.
    """
    tags = set(a.get("tags") or [])
    if (a.get("source_type") == "world_news" or a.get("perspective") == "news"
            or tags & NEWS_TAGS or a.get("source_category") == "news"):
        return "news"
    if tags & CHURCH_TAGS or a.get("source_category") in CHURCH_SOURCE_CATEGORIES:
        return "church"
    return "commentary"


def is_audio_video(a: dict) -> bool:
    """True for podcast episodes and videos, whatever feed they came from."""
    if a.get("media_format"):
        return True
    parts = urlsplit(a.get("url") or "")
    host = (parts.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
        return True
    title = (a.get("title") or "").lower()
    return "/podcast" in parts.path.lower() or title.startswith(("podcast:", "video:"))


def _cap_audio_video(ranked: list[dict], limit: int = MAIN_LANE_MAX_AUDIO_VIDEO) -> list[dict]:
    """Drop audio/video items beyond the top `limit` from an importance-ranked list."""
    kept, n = [], 0
    for a in ranked:
        if is_audio_video(a):
            if n >= limit:
                continue
            n += 1
        kept.append(a)
    return kept


def format_duration(seconds) -> str:
    """'15 min', '1 hr 33 min', or '' when unknown."""
    try:
        minutes = round(int(seconds) / 60)
    except (TypeError, ValueError):
        return ""
    if minutes <= 0:
        return ""
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} hr {rest} min" if rest else f"{hours} hr"


def _pick_lead(pool: list[dict], n: int) -> list[dict]:
    """Top `n` by importance, one per source."""
    picks, sources = [], set()
    for a in pool:
        src = a.get("source_name", "")
        if src in sources:
            continue
        picks.append(a)
        sources.add(src)
        if len(picks) >= n:
            break
    return picks


def _build_debate(articles: list[dict], pairings: list[dict]) -> list[dict]:
    """Side-by-side pairs. Claude's point/counterpoint pairings first; if there
    are none, fall back to the scorer's supportive vs. critical opposing pairs
    (same topic_cluster). Every pair, including cached ones, must pass
    point_counterpoint.validate_pair(). Returns [] when nothing pairs, so the
    module is omitted.
    """
    from curator.point_counterpoint import validate_pair
    by_url = {a.get("url"): a for a in articles}
    debates, used = [], set()
    for p in pairings or []:
        # Cached pairings (regenerate_daily.py) carry only title + url, so use
        # the full article dict when we have it.
        point, counter = p.get("point"), p.get("counterpoint")
        point = by_url.get((point or {}).get("url"), point)
        counter = by_url.get((counter or {}).get("url"), counter)
        if not point or not counter:
            continue
        if point.get("url") in used or counter.get("url") in used:
            continue
        if validate_pair(point, counter):
            continue
        d = {"topic": p.get("topic", ""), "label_a": "Point", "label_b": "Counterpoint",
             "a": point, "b": counter, "kind": "claude"}
        # Theses ride along when the pairing (fresh or cached) recorded them;
        # the email only shows Claude pairs that state both.
        for key in ("thesis_a", "thesis_b"):
            if key in p:
                d[key] = p.get(key) or ""
        debates.append(d)
        used |= {point.get("url"), counter.get("url")}
        if len(debates) >= DEBATE_MAX_PAIRS:
            return debates

    clusters: dict = {}
    for a in articles:
        if a.get("opposing_pair") and a.get("url") not in used:
            clusters.setdefault(a.get("topic_cluster") or "", []).append(a)
    for cluster, group in clusters.items():
        pro = next((a for a in group if a.get("perspective") == "supportive"), None)
        con = next((a for a in group if a.get("perspective") == "critical"), None)
        if not cluster or not pro or not con or validate_pair(pro, con):
            continue
        debates.append({"topic": cluster.replace("_", " ").capitalize(),
                        "label_a": "Pro", "label_b": "Con", "a": pro, "b": con,
                        "kind": "scorer"})
        if len(debates) >= DEBATE_MAX_PAIRS:
            break
    return debates


def pulse_line(daily_summary: dict | None, max_words: int = 20) -> str:
    """First sentence of the Daily Pulse, capped at `max_words`, or ""."""
    if not daily_summary:
        return ""
    plain = (daily_summary.get("paragraphs_plain") or [""])[0] or ""
    if not plain:
        html = (daily_summary.get("paragraphs_html") or [""])[0] or ""
        plain = re.sub(r"<[^>]+>", "", html)
    plain = " ".join(plain.split())
    if not plain:
        return ""
    sentence = re.split(r"(?<=[.!?])\s", plain, maxsplit=1)[0]
    words = sentence.split()
    if len(words) > max_words:
        sentence = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return sentence


def updated_label(now: datetime | None = None) -> str:
    """'Updated 2:14 AM ET' from the actual render time."""
    try:
        from zoneinfo import ZoneInfo
        now = now or datetime.now(ZoneInfo("America/New_York"))
        return f"Updated {now.strftime('%-I:%M %p')} ET"
    except Exception:
        return "Updated daily"


def build_homepage_layout(articles: list[dict], pairings: list[dict] | None = None,
                          research_articles: list[dict] | None = None,
                          per_column: int = BOARD_PER_COLUMN,
                          media_items: list[dict] | None = None) -> dict:
    """Assign articles to homepage v2 sections. Each URL appears at most once.

    `media_items` are the role "media" feed items (main.py splits them off
    before scoring); they only ever reach the Watch and Listen lane.
    """
    ranked = sorted((a for a in articles if a.get("url") and a.get("role") != "media"),
                    key=_score, reverse=True)
    fresh = _cap_audio_video(
        [a for a in ranked if not a.get("previously_shown") and not a.get("catholic_capped")])

    lead_pool = [a for a in fresh if a.get("source_type") != "world_news"]
    top = _pick_lead(lead_pool, 1 + SUBLEAD_COUNT)
    lead, subleads = (top[0] if top else None), top[1:]
    placed = {a["url"] for a in top}

    debate = _build_debate(articles, [
        p for p in (pairings or [])
        if p.get("point", {}).get("url") not in placed
        and p.get("counterpoint", {}).get("url") not in placed
    ])
    for d in debate:
        placed |= {d["a"]["url"], d["b"]["url"]}

    research = []
    for r in research_articles or []:
        if r.get("url") and r["url"] not in placed:
            research.append(r)
            placed.add(r["url"])
        if len(research) >= RESEARCH_MAX:
            break

    # Worth Your Time excludes the top of the importance lane: lead block plus
    # the first rows of each board column, so depth picks aren't repeats.
    board_preview = {a["url"] for a in fresh[:1 + SUBLEAD_COUNT + 3 * 6]}
    worth_your_time = select_worth_your_time(articles, exclude_urls=placed | board_preview)
    placed |= {a["url"] for a in worth_your_time}

    watch_listen = select_watch_and_listen(media_items or [], exclude_urls=placed)
    for a in watch_listen:
        a["duration_display"] = format_duration(a.get("duration_seconds"))
    placed |= {a["url"] for a in watch_listen}
    # Podcast feeds and publisher feeds can link one episode with different
    # tracking params, so the board also compares canonical URLs to the lane.
    media_canon = {canonical_url(a["url"]) for a in watch_listen}

    columns = {key: [] for key, _ in BOARD_COLUMNS}
    per_source: dict = {}
    for a in fresh:
        if a["url"] in placed or canonical_url(a["url"]) in media_canon:
            continue
        key = board_column(a)
        src_key = (key, a.get("source_name", ""))
        if len(columns[key]) < per_column and per_source.get(src_key, 0) < BOARD_PER_SOURCE:
            columns[key].append(a)
            per_source[src_key] = per_source.get(src_key, 0) + 1
            placed.add(a["url"])

    board = [{"key": key, "label": label, "articles": columns[key]} for key, label in BOARD_COLUMNS]
    return {
        "lead": lead,
        "subleads": subleads,
        "debate": debate,
        "worth_your_time": worth_your_time,
        "watch_listen": watch_listen,
        "board": board,
        "research": research,
    }


def outbound_urls(layout: dict) -> list[str]:
    """Every article URL the layout links to, in page order."""
    urls = []
    if layout.get("lead"):
        urls.append(layout["lead"]["url"])
    urls += [a["url"] for a in layout.get("subleads", [])]
    for col in layout.get("board", []):
        urls += [a["url"] for a in col["articles"]]
    for d in layout.get("debate", []):
        urls += [d["a"]["url"], d["b"]["url"]]
    urls += [a["url"] for a in layout.get("worth_your_time", [])]
    urls += [a["url"] for a in layout.get("watch_listen", [])]
    urls += [r["url"] for r in layout.get("research", [])]
    return urls
