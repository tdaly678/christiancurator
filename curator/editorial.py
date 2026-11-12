"""
editorial.py: ideas over scandal in the lead block (Tom, 2026-11-12).

Tom read the Nov 12 email and the Lead was a news arrest with a plagiarism
story near the top of the board. He wants thinking, philosophy, theology and
praxis (how faith is lived: church practice, discipleship, preaching, family,
vocation) first, news second, scandal last. And the Daily Pulse "looks pretty
good", so the rest should follow its lead: the stories the Pulse draws on take
the Lead and the subleads.

Until now the lead block was the top 4 by importance (final_score), which is
news value. rank_lead_pool() orders the lead pool in explicit tiers instead:

  tier 0  Pulse-cited: an article the Pulse drew on (its reported source URLs,
          a link in its paragraphs, or a named author / outlet), in the order
          the Pulse mentions them. Any kind but scandal.
  tier 1  ideas pieces on a Pulse theme
  tier 2  other ideas pieces
  tier 3  commentary (politics, culture, data analysis with no ideas tag)
  tier 4  news, filler only when tiers 0 to 3 run out
  never   scandal, unless it is the dominant story of the day

Tiers 1 to 3 need final_score >= LEAD_MIN_SCORE; tier 0 needs
PULSE_CITED_MIN_SCORE. Within tiers 1 to 4 the order is
0.5 * importance + 0.5 * depth, the blend the Pulse itself reads by.

Dominant story (the high bar): a news or scandal story with final_score >=
DOMINANT_MIN_SCORE carried by DOMINANT_MIN_OUTLETS or more distinct outlets
(shared topic_cluster plus dedup also_from). Think a denomination-wide vote or
a national ruling, not one outlet's exclusive. It gets exactly one lead-block
slot, the first sublead, and takes the Lead only when nothing in tiers 0 to 3
qualifies.

No API clients here, so render-only scripts can import it.
"""

from __future__ import annotations

import html
import re

from curator.dedup import canonical_url
from curator.headline_voice import SCANDAL_RE

# The scorer's tags (curator/vocab.py) that mark theology, philosophy and praxis.
IDEAS_TAGS = {"theology", "apologetics", "church life", "missions", "devotional",
              "prayer", "family", "suffering", "work"}

KINDS = ("ideas", "commentary", "news", "scandal")

# "crisis" and "investigation" also describe essays ("a crisis of meaning",
# "an investigation of the Psalms"), so alone they mark a scandal only on a
# news report. Every other SCANDAL_RE term (abuse, lawsuit, arrested, fraud,
# plagiarism...) marks one wherever it appears.
WEAK_SCANDAL_TERMS = {"crisis", "investigation"}

LEAD_MIN_SCORE = 5.0
PULSE_CITED_MIN_SCORE = 3.0
DOMINANT_MIN_SCORE = 8.5
DOMINANT_MIN_OUTLETS = 4

TIER_PULSE_CITED = 0
TIER_PULSE_THEME = 1
TIER_IDEAS = 2
TIER_COMMENTARY = 3
TIER_NEWS = 4
TIER_EXCLUDED = 9

# Words too common in Pulse themes to tie an article to one.
_THEME_STOPWORDS = {
    "and", "the", "of", "in", "on", "for", "to", "a", "an", "vs", "versus", "with",
    "church", "christian", "christians", "christianity", "faith", "god", "evangelical",
    "evangelicals", "life", "public", "modern", "culture", "debate", "question",
}


def _title(a: dict) -> str:
    return a.get("rewritten_title") or a.get("title") or ""


def _score(a: dict) -> float:
    return a.get("final_score", a.get("score", 0)) or 0


def editorial_value(a: dict) -> float:
    """0.5 importance + 0.5 depth, as the Pulse ranks its sources."""
    importance = _score(a)
    depth = a.get("depth")
    if depth is None:
        depth = importance
    return 0.5 * importance + 0.5 * depth


def is_news_report(a: dict) -> bool:
    """Straight news, as opposed to essay, opinion, review or data analysis."""
    return (a.get("perspective") == "news"
            or a.get("source_type") == "world_news"
            or "news" in (a.get("tags") or []))


def is_scandal_story(a: dict) -> bool:
    """Scandal, misconduct, lawsuit, arrest, abuse-allegation or crisis news."""
    hits = {m.group(0).lower() for m in SCANDAL_RE.finditer(_title(a))}
    if not hits:
        return False
    return bool(hits - WEAK_SCANDAL_TERMS) or is_news_report(a)


def content_kind(a: dict) -> str:
    """"ideas" (theology, philosophy, praxis), "commentary", "news" or "scandal"."""
    if is_scandal_story(a):
        return "scandal"
    if is_news_report(a):
        return "news"
    if set(a.get("tags") or []) & IDEAS_TAGS:
        return "ideas"
    return "commentary"


def story_outlets(a: dict, pool: list[dict]) -> set[str]:
    """Distinct outlets carrying this story: the shared topic_cluster in the
    pool plus the dedup copies folded into it."""
    outlets = {a.get("source_name") or ""}
    outlets.update(a.get("also_from") or [])
    cluster = a.get("topic_cluster")
    if cluster and cluster != "unique":
        outlets.update(x.get("source_name") or "" for x in pool
                       if x.get("topic_cluster") == cluster)
    outlets.discard("")
    return outlets


def is_dominant_story(a: dict, pool: list[dict]) -> bool:
    """The high bar for news or scandal in the lead block (see module doc)."""
    return (_score(a) >= DOMINANT_MIN_SCORE
            and len(story_outlets(a, pool)) >= DOMINANT_MIN_OUTLETS)


# ── Pulse anchoring ──────────────────────────────────────────────────────────

def _pulse_text_and_links(daily_summary: dict) -> tuple[str, list[tuple[int, int, str]]]:
    """The Pulse as plain text, plus (start, end, url) for each link's anchor
    text in it, so links and named writers can be ordered by position."""
    paras = [p for p in daily_summary.get("paragraphs_html") or [] if p]
    if not paras:
        return " ".join(p for p in daily_summary.get("paragraphs_plain") or [] if p), []
    text, links, open_link = "", [], None
    for para in paras:
        last = 0
        for m in re.finditer(r"<[^>]+>", para):
            text += html.unescape(para[last:m.start()])
            last = m.end()
            href = re.match(r'<a\s[^>]*href="(https?://[^"]+)"', m.group(0))
            if href:
                open_link = (len(text), href.group(1))
            elif m.group(0).startswith("</a") and open_link:
                links.append((open_link[0], len(text), open_link[1]))
                open_link = None
        text += html.unescape(para[last:]) + " "
    return text, links


def _name_position(name: str, text: str, skip: list[tuple[int, int, str]]) -> int | None:
    """First whole-word mention of `name` outside any link's anchor text."""
    name = (name or "").strip()
    if len(name) < 3:
        return None
    for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text):
        if not any(start <= m.start() < end for start, end, _ in skip):
            return m.start()
    return None


def pulse_cited_urls(daily_summary: dict | None, articles: list[dict]) -> list[str]:
    """Canonical URLs of the articles the Pulse drew on, in mention order.

    The URLs the Pulse reported (`source_urls`) come first, in its order.
    Then links in its paragraphs and named writers and outlets, ordered by
    where they appear. A named author marks that author's article; a named
    outlet marks its best piece (by editorial_value), unless the name was
    already used as an author ("Russell Moore at Christianity Today" is the
    CT piece, not Moore's own newsletter). Names inside a link's anchor text
    belong to that link. When the summary lists `candidate_urls`, name
    matches are limited to them, since those are what the Pulse read.
    """
    if not daily_summary or daily_summary.get("fallback"):
        return []
    by_canon = {canonical_url(a["url"]): a for a in articles if a.get("url")}
    order: list[str] = []

    def add(url: str) -> None:
        canon = canonical_url(url)
        if canon in by_canon and canon not in order:
            order.append(canon)

    for url in daily_summary.get("source_urls") or []:
        add(url)

    text, links = _pulse_text_and_links(daily_summary)
    mentions: list[tuple[int, str]] = [(start, url) for start, _, url in links]
    candidates = daily_summary.get("candidate_urls")
    if candidates:
        allowed = {canonical_url(u) for u in candidates}
        pool = [a for c, a in by_canon.items() if c in allowed]
    else:
        pool = list(by_canon.values())

    author_names = set()
    for a in pool:
        author, source = (a.get("author") or "").strip(), (a.get("source_name") or "").strip()
        if author and author.lower() != source.lower():
            pos = _name_position(author, text, links)
            if pos is not None:
                mentions.append((pos, a["url"]))
                author_names.add(author.lower())
    best_by_source: dict[str, dict] = {}
    for a in pool:
        source = (a.get("source_name") or "").strip()
        if source.lower() in author_names:
            continue
        if source not in best_by_source or editorial_value(a) > editorial_value(best_by_source[source]):
            best_by_source[source] = a
    for source, a in best_by_source.items():
        pos = _name_position(source, text, links)
        if pos is not None:
            mentions.append((pos, a["url"]))
    for _, url in sorted(mentions, key=lambda m: m[0]):
        add(url)
    return order


def _stem(word: str) -> str:
    return word[:6]


def pulse_theme_stems(daily_summary: dict | None) -> set[str]:
    """Distinctive word stems from the Pulse's theme labels."""
    if not daily_summary:
        return set()
    stems = set()
    for theme in daily_summary.get("themes") or []:
        for w in re.findall(r"[a-z]+", str(theme).lower()):
            if len(w) >= 4 and w not in _THEME_STOPWORDS:
                stems.add(_stem(w))
    return stems


def on_pulse_theme(a: dict, stems: set[str]) -> bool:
    """A theme word in the title, or two distinct ones in the summary."""
    if not stems:
        return False
    title = {_stem(w) for w in re.findall(r"[a-z]+", _title(a).lower()) if len(w) >= 4}
    if title & stems:
        return True
    body = re.sub(r"<[^>]+>", " ", a.get("summary") or "").lower()
    summary = {_stem(w) for w in re.findall(r"[a-z]+", body) if len(w) >= 4}
    return len(summary & stems) >= 2


# ── Lead-block ranking ───────────────────────────────────────────────────────

def lead_tier(a: dict, cited: dict[str, int], stems: set[str]) -> int:
    kind = content_kind(a)
    if kind == "scandal":
        return TIER_EXCLUDED
    score = _score(a)
    if canonical_url(a.get("url") or "") in cited and score >= PULSE_CITED_MIN_SCORE:
        return TIER_PULSE_CITED
    if kind == "news":
        return TIER_NEWS
    if score < LEAD_MIN_SCORE:
        return TIER_EXCLUDED
    if kind == "ideas":
        return TIER_PULSE_THEME if on_pulse_theme(a, stems) else TIER_IDEAS
    return TIER_COMMENTARY


def rank_lead_pool(pool: list[dict], daily_summary: dict | None = None,
                   all_articles: list[dict] | None = None) -> tuple[list[dict], dict | None]:
    """(ordered lead candidates, dominant story or None).

    `pool` is already filtered for lead eligibility and sorted by importance.
    `all_articles` (default `pool`) is what Pulse names and story outlet counts
    are matched against. Excluded items (scandal, below the floor) are dropped;
    the dominant story, if any, is returned separately for its reserved slot.
    """
    everything = all_articles if all_articles is not None else pool
    cited = {c: i for i, c in enumerate(pulse_cited_urls(daily_summary, everything))}
    stems = pulse_theme_stems(daily_summary)
    dominant = next((a for a in pool if content_kind(a) in ("news", "scandal")
                     and is_dominant_story(a, everything)), None)
    keyed = []
    for a in pool:
        if a is dominant:
            continue
        tier = lead_tier(a, cited, stems)
        if tier == TIER_EXCLUDED:
            continue
        within = (cited[canonical_url(a["url"])] if tier == TIER_PULSE_CITED
                  else -editorial_value(a))
        keyed.append(((tier, within), a))
    keyed.sort(key=lambda t: t[0])
    return [a for _, a in keyed], dominant


def board_sort_key(a: dict, pool: list[dict]) -> tuple:
    """Board columns keep importance order, but a scandal story that is not
    the dominant story sits below every other item in its column."""
    demoted = content_kind(a) == "scandal" and not is_dominant_story(a, pool)
    return (demoted, -_score(a))
