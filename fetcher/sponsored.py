"""Sponsored and vendor guest posts, dropped at ingest.

Carey Nieuwhof's site (and others like it) runs paid posts written by the
sponsor's own staff. They open with a disclosure line:

    This post is in partnership with Subsplash, written by Jeff Harvey, ...
    This is a guest post by Josh Burnett, Founder of Church.Tech ...
    This is a guest post by Marc Estes, CEO of VisitorReach ...

Real guest posts open the same way but name a pastor:

    This is a guest post by Andy Searles, Pastor of Church Together ...

Only the opening of the body is checked (disclosures sit at the top), so a
sentence like "a church plant in partnership with local churches" deep in an
ordinary article never matches. A guest post counts as vendor content only
when its disclosure names a company role (founder, CEO, marketing...) and
no ministry role (pastor, chaplain, minister...).
"""
from __future__ import annotations

import html
import re

OPENING_CHARS = 400

_PARTNERSHIP_RE = re.compile(
    r"\b(?:this|the following)\s+(?:post|article|episode|content|piece)\s+"
    r"(?:is|was)\s+(?:written\s+|brought to you\s+|published\s+)?"
    r"(?:in\s+partnership\s+with|sponsored\s+by|presented\s+by|paid\s+for\s+by)\b"
    r"|\bthis\s+is\s+a\s+sponsored\s+(?:post|article|episode)\b"
    r"|^\s*(?:sponsored(?:\s+by)?|paid\s+partnership|in\s+partnership\s+with)\b",
    re.IGNORECASE,
)

_GUEST_RE = re.compile(r"\bthis\s+is\s+a\s+guest\s+post\s+by\b([^.]{0,200})", re.IGNORECASE)

_VENDOR_ROLE_RE = re.compile(
    r"\b(?:co-?founder|founder|ceo|cto|coo|cmo|chief\s+\w+\s+officer|president|"
    r"vice\s+president|vp|head\s+of\s+(?:growth|marketing|sales|partnerships)|"
    r"marketing|sales|product\s+manager|account\s+executive)\b",
    re.IGNORECASE,
)

_MINISTRY_ROLE_RE = re.compile(
    r"\b(?:pastor|chaplain|minister|priest|elder|rector|reverend|rev\.?|"
    r"missionary|church\s+planter|seminary|professor)\b",
    re.IGNORECASE,
)


def _opening(text: str) -> str:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text or "", flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()[:OPENING_CHARS]


def sponsored_disclosure(*texts: str) -> str | None:
    """Return the matched disclosure when a body opens like a paid post, else None."""
    for text in texts:
        opening = _opening(text)
        if not opening:
            continue
        m = _PARTNERSHIP_RE.search(opening)
        if m:
            return opening[m.start():m.start() + 160].strip()
        g = _GUEST_RE.search(opening)
        if g and _VENDOR_ROLE_RE.search(g.group(1)) and not _MINISTRY_ROLE_RE.search(g.group(1)):
            return g.group(0).strip()[:160]
    return None


def is_sponsored(article: dict) -> bool:
    return sponsored_disclosure(article.get("full_content", ""), article.get("summary", "")) is not None
