"""Evangelical mission gate for general world-news feeds (Tom, 2026-10-31).

BBC, NYT and WSJ world feeds are fetched so the News board can carry stories
about persecution, religious liberty and the church abroad. They also carry
wars, disasters, foreign politics and markets with no faith angle at all.
Those must never reach the lead or the board.

`has_faith_hook(title, summary)` is a deterministic keyword check: the title or
summary has to name Christianity, the church, religion, persecution, religious
liberty or a core life issue. `is_off_mission(article)` is True for a
`source_type: "world_news"` item without that hook. Christian outlets are not
gated here (their framing is the faith angle), except their general news
briefs: WORLD's Sift and Christian Post /news/ items (is_news_brief(), Nov 22
2026).

No API clients here, so render-only scripts can import it.
"""
import re

FAITH_HOOK_RE = re.compile(
    r"\bchristians?\b|\bchristianity\b|\bchrist\b|\bjesus\b|\bgod\b|\bbible\b|\bbiblical\b|\bgospel\b"
    r"|\bchurch(es)?\b|\bmegachurch|\bchapel\b|\bcathedral\b|\bparish|\bdiocese|\bcongregation"
    r"|\bdenomination|\bpastors?\b|\bpriests?\b|\bclergy|\bbishops?\b|\bpope\b|\bpapal\b|\bvatican\b"
    r"|\bnuns?\b|\bmonks?\b|\bmonaster|\bseminar(y|ies)\b|\bmissionar|\bevangelic|\bprotestant"
    r"|\bcatholic|\bbaptists?\b|\bpresbyterian|\bmethodist|\banglican|\blutheran|\bpentecostal"
    r"|\borthodox church|\bcoptic|\bworship|\bprayers?\b|\bpray(ed|ing|s)?\b|\btheolog"
    r"|\breligio(n|us|ns)\b|\b(?<!good )(?<!bad )faith\b|\bfaith-based|\bbelievers?\b"
    r"|\bpersecut|\bblasphemy|\bapostasy|\bmartyr|\bchristmas\b|\beaster\b|\bholy\b"
    r"|\babortion|\bpro-life|\beuthanasia|\bassisted (dying|suicide)",
    re.IGNORECASE,
)


def has_faith_hook(title: str, summary: str = "") -> bool:
    """True when the headline or summary carries a Christian or religious angle."""
    return bool(FAITH_HOOK_RE.search(f"{title or ''} {summary or ''}"))


# News briefs from Christian outlets that wire general news (Nov 22 2026, S1
# 2.2): WORLD's The Sift and Christian Post news items. These carry stories
# like "Iranian agent gets more than 27-year sentence for Trump murder plot",
# so they face the same faith-hook gate as world news. Essays, opinion and
# reporting sections of the same outlets are not gated.
BRIEF_URL_RE = re.compile(
    r"^https?://(?:www\.)?(?:wng\.org/(?:sift|briefs?)/|christianpost\.com/(?:news|briefs?)/)",
    re.IGNORECASE,
)


# Extra hooks for Christian-outlet briefs only: issues these outlets cover as
# part of their beat that the world-news gate deliberately leaves out.
BRIEF_HOOK_RE = re.compile(
    r"\bministr(y|ies)\b|\bevangelis|\bsatan|\bmifepristone|\btransgender|\btrans\b|\btitle ix\b"
    r"|\bbiological sex\b|\bgender\b|\bantisemit|\bjewish\b|\bjews\b|\bmuslims?\b|\bislam"
    r"|\bhindu|\bADF\b|\balliance defending|\bmarriage\b|\bsexuality\b|\bIVF\b|\bsurrogacy"
    r"|\bschool choice\b|\bchaplain|\bsermon|\bnarnia\b|\bthe chosen\b|\bhymn|\bdeath (penalty|sentence)"
    r"|\bexecution|\bbirth ?rates?\b|\bfertility\b|\bconscience\b|\bpornograph",
    re.IGNORECASE,
)


def is_news_brief(article: dict) -> bool:
    """True for a WORLD Sift or Christian Post news brief."""
    return bool(BRIEF_URL_RE.search(article.get("url") or ""))


def is_off_mission(article: dict) -> bool:
    """True for a general world-news item, or a WORLD / Christian Post news
    brief, with no faith, church or liberty hook."""
    title = article.get("title", "")
    summary = (article.get("summary") or "")[:500]
    if article.get("source_type") == "world_news":
        return not has_faith_hook(title, summary)
    if is_news_brief(article):
        original = article.get("original_title") or ""
        return not (has_faith_hook(f"{title} {original}", summary)
                    or BRIEF_HOOK_RE.search(f"{title} {original} {summary}"))
    return False
