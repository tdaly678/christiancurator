"""
voice_filters.py — decides whether a byline is a real person who deserves a
/voices/<slug>/ page.

Shared by curator/voice_generator.py (new pages from today's articles),
scripts/backfill_voices_data.py (orphan pages on disk), and the junk-voice
review report, so the rules live in exactly one place.
"""

from __future__ import annotations

import re

# /voices/<slug>/ category hub pages built by scripts/build_voice_hubs.py.
# They live alongside person pages but are not people. Keep in sync with
# CATEGORIES in that script.
HUB_SLUGS = frozenset({
    "pastors", "theologians-scholars", "apologists", "bible-teachers",
    "journalists", "ministry-leaders", "writers", "speakers-creators",
})

# Slug tokens that mark an institutional byline rather than a person.
_INSTITUTIONAL_TOKENS = frozenset({
    "staff", "editor", "editors", "editorial", "team", "admin", "administrator",
    "contributor", "contributors", "newsroom", "desk", "press", "news",
    "magazine", "ministries", "ministry", "podcast", "institute", "coalition",
    "reformation", "reformer", "report", "journal", "blog", "webmaster",
    "anonymous", "unknown", "guest",
    # job titles appended to a byline ("aamna-mohdin-community-affairs-correspondent")
    "correspondent", "reporter", "columnist",
})

# Well-known placeholder names (zhang-san is the Chinese "John Doe").
_PLACEHOLDER_SLUGS = frozenset({
    "john-doe", "jane-doe", "zhang-san", "li-si", "test-author", "author",
})

# Leading honorifics that end up baked into the slug ("dr-owen-anderson").
_HONORIFIC_PREFIX_RE = re.compile(
    r"^(dr|rev|pastor|elder|bishop|fr|father|prof|professor|intercessor|apostle|prophet)-")


def junk_reason(slug: str) -> str | None:
    """Return why a voice slug looks like junk, or None if it looks like a person."""
    if slug in HUB_SLUGS:
        return None
    if slug in _PLACEHOLDER_SLUGS:
        return "placeholder name"
    if "ruling-elder" in slug:
        return "role description, not a name"
    if "-and-" in slug:
        return "multiple authors in one byline (-and-)"
    tokens = slug.split("-")
    hits = _INSTITUTIONAL_TOKENS.intersection(tokens)
    if hits:
        return f"institutional byline ({', '.join(sorted(hits))})"
    if slug == "guest-author" or slug.startswith("guest-"):
        return "guest-author byline"
    if len(tokens) == 1:
        return "bare handle / single token (no surname)"
    if any(ch.isdigit() for ch in slug):
        return "contains digits (looks like a username)"
    if _HONORIFIC_PREFIX_RE.match(slug):
        return "honorific baked into slug (likely duplicate of the plain-name page)"
    return None


def is_voice_worthy(slug: str) -> bool:
    return slug not in HUB_SLUGS and junk_reason(slug) is None
