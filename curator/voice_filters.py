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
    # wire services and secular newsrooms ("guardian-staff-and-agencies", "reuters")
    "agency", "agencies", "wire", "wires", "reuters", "afp", "upi", "bloomberg",
    "cnn", "bbc", "npr", "board", "bureau", "associated",
    # organisation words ("relevant-media-group", "crossway-publishing")
    "media", "group", "inc", "llc", "foundation", "society", "association",
    "council", "seminary", "university", "college", "publishing", "publishers",
    "books", "radio", "network", "studios", "productions", "fellowship",
    "alliance", "initiative", "project", "online", "digital", "times", "herald",
    "gazette", "daily",
})

# Raw-byline patterns that mean "not a single person" before any slugging.
# Co-bylines are rejected whole rather than split: "X and Y" / "X & Y" / "X, Y"
# were the single biggest source of junk pages (72 of 106 in the 2026-10-25 review).
_COBYLINE_RE = re.compile(r"\s(?:and|with|&)\s|&|[,;/|]|\+", re.IGNORECASE)
# Trailing ", Jr." / ", PhD" etc. are not a second author.
_SUFFIX_RE = re.compile(r",\s*(?:jr|sr|ii|iii|iv|phd|ph\.d|md|m\.d|esq|dmin|d\.min|thm|th\.m)\.?\s*$",
                        re.IGNORECASE)
_URL_RE = re.compile(r"https?://|www\.|\.(?:com|org|net|io|co|uk)\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

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
    if "-and-" in slug or "-with-" in slug:
        return "multiple authors in one byline (-and-/-with-)"
    tokens = slug.split("-")
    if tokens[0] == "the":
        return "organisation name (leading 'the')"
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


def name_junk_reason(name: str) -> str | None:
    """Return why a raw byline (before slugging) is not one person, or None.

    Catches what slugging hides: "X & Y" slugs to "x-y", "@handle" to "handle",
    and an email or URL loses its punctuation.
    """
    name = (name or "").strip()
    if not name:
        return "empty byline"
    if _EMAIL_RE.search(name):
        return "email address"
    if _URL_RE.search(name):
        return "URL or domain"
    if "@" in name:
        return "social handle (@)"
    if _COBYLINE_RE.search(_SUFFIX_RE.sub("", name)):
        return "multiple authors in one byline"
    letters = [c for c in name if c.isalpha()]
    if letters and name == name.lower():
        return "all-lowercase byline (username)"
    if letters and len(letters) > 3 and name == name.upper() and " " not in name:
        return "all-caps single token (brand)"
    return None


def source_creates_voices(article: dict) -> bool:
    """Whether an article's source may mint voice pages at all.

    Secular feeds (source_type="world_news": AP, BBC, NYT, WSJ, Guardian, WaPo)
    are curated for their content but their reporters are not evangelical voices;
    research shops opt out with "creates_voices": False in fetcher/sources.py.
    """
    if article.get("source_type") == "world_news":
        return False
    return article.get("creates_voices") is not False


def is_voice_worthy(slug: str, name: str | None = None) -> bool:
    """True if slug (and, when given, the raw byline) look like one real person."""
    if slug in HUB_SLUGS or junk_reason(slug) is not None:
        return False
    return name is None or name_junk_reason(name) is None
