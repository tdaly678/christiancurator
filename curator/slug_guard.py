"""Junk-slug guard for the Voices directory.

Deliberately dependency free. `curator/voice_generator.py` imports `anthropic`,
so scripts that only need the guard cannot import it from there; this module
stays importable from any script with no third-party packages installed.

A "junk" slug is a byline that was never a person: wire-service credits,
newsroom collective bylines, desk titles, and two-reporter mashups. They were
creating thin /voices/ pages that carried no editorial value and showed up in
Search Console as indexed noise.
"""
from __future__ import annotations

import re

# Patterns that identify a slug as a non-person byline.
# Kept conservative on purpose: a false positive deletes a real person's page.
JUNK_SLUG_PATTERNS: list[re.Pattern] = [
    re.compile(r"-and-agenc(y|ies)$"),          # richard-luscombe-and-agency
    re.compile(r"^staff-and-agenc(y|ies)$"),    # staff-and-agencies
    re.compile(r"-staff-and-agenc(y|ies)$"),    # guardian-staff-and-agencies
    re.compile(r"^words-by-"),                  # words-by-sam-wollaston
    re.compile(r"-correspondent$"),             # ...-community-affairs-correspondent
    re.compile(r"-editor$"),
    re.compile(r"^(staff|newsroom|editorial-staff|wire|agencies)$"),
    re.compile(r"-of-[a-z0-9-]+-and-"),         # david-hammer-of-wwl-louisiana-and-...
]

# Slugs that the patterns above do not catch but are still not people.
EXPLICIT_JUNK_SLUGS: set[str] = {
    "fm-ai",
    "roque-planas-and-agencies",
    "amelia-nierenberg-and-matthew-mpoke-bigg",
    "anton-troianovski-and-david-e-sanger",
    "jonathan-swan-and-david-e-sanger",
    "golden-matonga-and-matthew-mpoke-bigg",
    "max-kim-and-chang-w-lee",
}

# Mashups of two REAL people. These must be split into separate voice pages,
# never deleted. `prune_junk_voices.py` reports them and leaves them alone.
SPLIT_NOT_DELETE: dict[str, tuple[str, ...]] = {
    "john-stonestreet-and-s-michael-craven": ("john-stonestreet", "s-michael-craven"),
}


def is_junk_slug(slug: str) -> bool:
    """True if `slug` is a non-person byline that should never get a voice page."""
    if not slug:
        return True
    slug = slug.strip().lower()
    if slug in SPLIT_NOT_DELETE:
        return False
    if slug in EXPLICIT_JUNK_SLUGS:
        return True
    return any(p.search(slug) for p in JUNK_SLUG_PATTERNS)


def needs_split(slug: str) -> tuple[str, ...]:
    """Return the component slugs if `slug` is a two-person mashup, else ()."""
    return SPLIT_NOT_DELETE.get((slug or "").strip().lower(), ())
