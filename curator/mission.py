"""Evangelical mission gate for general world-news feeds (Tom, 2026-10-31).

BBC, NYT and WSJ world feeds are fetched so the News board can carry stories
about persecution, religious liberty and the church abroad. They also carry
wars, disasters, foreign politics and markets with no faith angle at all.
Those must never reach the lead or the board.

`has_faith_hook(title, summary)` is a deterministic keyword check: the title or
summary has to name Christianity, the church, religion, persecution, religious
liberty or a core life issue. `is_off_mission(article)` is True for a
`source_type: "world_news"` item without that hook. Christian outlets are never
gated here; their framing is the faith angle.

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


def is_off_mission(article: dict) -> bool:
    """True for a general world-news item with no faith, church or liberty hook."""
    if article.get("source_type") != "world_news":
        return False
    return not has_faith_hook(article.get("title", ""), (article.get("summary") or "")[:500])
